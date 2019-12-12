# -*- coding: utf-8 -*-
__all__ = ('Statement', 'StatementDB')

from typing import FrozenSet, Dict, Any, List, Iterator, Iterable
import json
import attr
import logging

from bugzoo.util import indent
from bugzoo.client import Client as BugZooClient
from bugzoo.core.bug import Bug as Snapshot
from bugzoo.core.container import Container

from .core import FileLocationRange, FileLocation, FileLine
from .exceptions import BondException
from .util import abs_to_rel_flocrange, rel_to_abs_flocrange
from .insertions import InsertionPointDB, InsertionPoint

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@attr.s(frozen=True, slots=True, auto_attribs=True)
class Statement:
    content: str
    canonical: str
    kind: str  # FIXME this is super memory inefficient
    location: FileLocationRange
    reads: FrozenSet[str]
    writes: FrozenSet[str]
    visible: FrozenSet[str]
    declares: FrozenSet[str]
    live_before: FrozenSet[str]
    requires_syntax: FrozenSet[str]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'Statement':
        location = FileLocationRange.from_string(d['location'])
        return Statement(d['content'],
                         d['canonical'],
                         d['kind'],
                         location,
                         frozenset(d.get('reads', [])),
                         frozenset(d.get('writes', [])),
                         frozenset(d.get('visible', [])),
                         frozenset(d.get('decls', [])),
                         frozenset(d.get('live_before', [])),
                         frozenset(d.get('requires_syntax', [])))

    def to_dict(self) -> Dict[str, Any]:
        return {'content': self.content,
                'canonical': self.canonical,
                'kind': self.kind,
                'location': str(self.location),
                'live_before': [v for v in self.live_before],
                'reads': [v for v in self.reads],
                'writes': [v for v in self.writes],
                'decls': [v for v in self.declares],
                'visible': [v for v in self.visible],
                'requires_syntax': list(self.requires_syntax)}


class StatementDB:
    @staticmethod
    def build(client_bugzoo: BugZooClient,
              snapshot: Snapshot,
              files: List[str],
              container: Container,
              *,
              ignore_exit_code: bool = False
              ) -> 'StatementDB':
        out_fn = "statements.json"
        logger.debug("building statement database for snapshot [%s]",
                     snapshot.name)
        logger.debug("fetching statements from files: %s", ', '.join(files))

        cmd = "kaskara-statement-finder {}".format(' '.join(files))
        workdir = snapshot.source_dir
        logger.debug("executing statement finder [%s]: %s", workdir, cmd)
        outcome = client_bugzoo.containers.exec(container, cmd, context=workdir)  # noqa
        logger.debug("executed statement finder [%d]:\n%s",
                     outcome.code, indent(outcome.output, 2))

        if not ignore_exit_code and outcome.code != 0:
            msg = "kaskara-statement-finder exited with non-zero code: {}"
            msg = msg.format(outcome.code)
            raise BondException(msg)  # FIXME

        logger.debug('reading statement analysis results from file: %s',
                     out_fn)
        output = client_bugzoo.files.read(container, out_fn)
        jsn = json.loads(output)  # type: List[Dict[str, Any]]
        db = StatementDB.from_dict(jsn, snapshot)
        logger.debug("finished reading statement analysis results")
        return db

    @staticmethod
    def from_file(fn: str, snapshot: Snapshot) -> 'StatementDB':
        logger.debug("reading statement database from file: %s", fn)
        with open(fn, 'r') as f:
            d = json.load(f)
        db = StatementDB.from_dict(d, snapshot)
        logger.debug("read statement database from file: %s", fn)
        return db

    @staticmethod
    def from_dict(d: List[Dict[str, Any]]) -> 'StatementDB':
        return StatementDB(Statement.from_dict(dd) for dd in d)

    def __init__(self, statements: Iterable[Statement]) -> None:
        self.__statements = statements
        logger.debug("indexing statements by file")
        self.__file_to_statements = {}  # type: Dict[str, List[Statement]]
        for statement in statements:
            filename = statement.location.filename
            if filename not in self.__file_to_statements:
                self.__file_to_statements[filename] = []
            self.__file_to_statements[filename].append(statement)
        summary = ["  {}: {} statements".format(fn, len(stmts))
                   for (fn, stmts) in self.__file_to_statements.items()]
        logger.debug("indexed statements by file:\n%s", '\n'.join(summary))

    def __iter__(self) -> Iterator[Statement]:
        yield from self.__statements

    def in_file(self, fn: str) -> Iterator[Statement]:
        """
        Returns an iterator over all of the statements belonging to a file.
        """
        yield from self.__file_to_statements.get(fn, [])

    def at_line(self, line: FileLine) -> Iterator[Statement]:
        """
        Returns an iterator over all of the statements located at a given line.
        """
        num = line.num
        for stmt in self.in_file(line.filename):
            if stmt.location.start.line == num:
                yield stmt

    def insertions(self) -> InsertionPointDB:
        logger.debug("computing insertion points")
        points = []  # type: List[InsertionPoint]
        for stmt in self:
            location = FileLocation(stmt.location.filename,
                                    stmt.location.stop)
            point = InsertionPoint(location, stmt.visible)

            # FIXME do not insert after a return

            points.append(point)
        db = InsertionPointDB(points)
        logger.debug("computed insertion points")
        return db

    def to_dict(self) -> List[Dict[str, Any]]:
        return [stmt.to_dict() for stmt in self.__statements]

    def to_file(self, fn: str) -> None:
        logger.debug("writing statement database to file: %s", fn)
        d = self.to_dict()
        with open(fn, 'w') as f:
            json.dump(d, f)
        logger.debug("wrote statement database to file: %s", fn)

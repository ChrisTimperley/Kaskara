__all__ = ['FunctionDesc', 'FunctionDB']

from typing import List, Dict, Tuple, Optional, Iterator, Iterable, Any
import json
import attr

from bugzoo.client import Client as BugZooClient
from bugzoo.core.bug import Bug as Snapshot
from bugzoo.core.container import Container

from .core import FileLocationRange, FileLocation
from .exceptions import BondException
from .util import abs_to_rel_flocrange


@attr.s(frozen=True)
class FunctionDesc(object):
    name = attr.ib(type=str)
    location = attr.ib(type=FileLocationRange)
    body = attr.ib(type=FileLocationRange)
    return_type = attr.ib(type=str)
    is_global = attr.ib(type=bool)
    is_pure = attr.ib(type=bool)

    @staticmethod
    def from_dict(d: Dict[str, Any],
                  snapshot: Snapshot
                  ) -> 'FunctionDesc':
        name = d['name']
        location = FileLocationRange.from_string(d['location'])
        location = abs_to_rel_flocrange(snapshot.source_dir, location)
        body = FileLocationRange.from_string(d['body'])
        body = abs_to_rel_flocrange(snapshot.source_dir, body)
        return_type = d['return-type']
        is_global = d['global']
        is_pure = d['pure']
        return FunctionDesc(name=name,
                            location=location,
                            body=body,
                            return_type=return_type,
                            is_global=is_global,
                            is_pure=is_pure)

    @property
    def filename(self) -> str:
        return self.location.filename

    def to_dict(self) -> Dict[str, Any]:
        return {'name': self.name,
                'location': str(self.location),
                'body': str(self.body),
                'return_type': self.return_type,
                'is_global': self.is_global,
                'is_pure': self.is_pure}


class FunctionDB(object):
    @staticmethod
    def from_dict(d: List[Dict[str, Any]],
                  snapshot: Snapshot
                  ) -> 'FunctionDB':
        return FunctionDB(FunctionDesc.from_dict(desc, snapshot) for desc in d)

    @staticmethod
    def build(client_bugzoo: BugZooClient,
              snapshot: Snapshot,
              files: List[str],
              container: Container
              ) -> 'FunctionDB':
        out_fn = "functions.json"
        cmd = "kaskara-function-scanner {}".format(' '.join(files))
        workdir = snapshot.source_dir
        outcome = client_bugzoo.containers.exec(container, cmd, context=workdir)

        if outcome.code != 0:
            msg = "kaskara-function-scanner exited with non-zero code: {}"
            msg = msg.format(outcome.code)
            raise BondException(msg)

        output = client_bugzoo.files.read(container, out_fn)
        jsn = json.loads(output)  # type: List[Dict[str, Any]]
        funcs = [FunctionDesc.from_dict(d, snapshot) for d in jsn]
        return FunctionDB(funcs)

    def __init__(self, functions: Iterable[FunctionDesc]) -> None:
        self.__filename_to_functions = \
            {}  # type: Dict[str, List[FunctionDesc]]
        for f in functions:
            if f.filename not in self.__filename_to_functions:
                self.__filename_to_functions[f.filename] = []
            self.__filename_to_functions[f.filename].append(f)

    def encloses(self,
                 location: FileLocation
                 ) -> Optional[FunctionDesc]:
        """
        Returns the function, if any, that encloses a given location.
        """
        for func in self.in_file(location.filename):
            if location in func.location:
                return func
        return None

    def in_file(self, filename: str) -> Iterator[FunctionDesc]:
        """
        Returns an iterator over all of the functions definitions that are
        contained within a given file.
        """
        yield from self.__filename_to_functions.get(filename, [])

    def to_dict(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self.__filename_to_functions.values()]

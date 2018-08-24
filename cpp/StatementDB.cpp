#include "StatementDB.h"

#include <iostream>
#include <fstream>

#include "util.h"

using json = nlohmann::json;
using namespace kaskara;

namespace kaskara {

StatementDB::StatementDB() : contents()
{ }

StatementDB::~StatementDB()
{ }

StatementDB::Entry::Entry(std::string const &location,
                          std::string const &content)
  : location(location),
    content(content),
    writes(),
    reads()
{ }

json const StatementDB::Entry::to_json() const
{
  json j_reads = json::array();
  json j_writes = json::array();
  json j = {
    {"location", location},
    {"content", content},
    {"reads", j_reads},
    {"writes", j_writes}
  };
  return j;
}

void StatementDB::add(clang::ASTContext const *ctx, clang::Stmt const *stmt)
{
  clang::SourceRange source_range = stmt_to_range(*ctx, stmt);
  std::string loc_str = build_loc_str(source_range, ctx);
  std::string txt = read_source(*ctx, source_range);

  // FIXME compute read and write information

  contents.emplace_back(loc_str, txt);
}

json StatementDB::to_json() const
{
  json j = json::array();
  for (auto &e : contents)
    j.push_back(e.to_json());
  return j;
}

void StatementDB::dump() const
{
  std::cout << std::setw(2) << to_json() << std::endl;
}

void StatementDB::to_file(const std::string &fn) const
{
  std::ofstream o(fn);
  o << std::setw(2) << to_json() << std::endl;
}

} // kaskara
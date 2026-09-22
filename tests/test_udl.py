from pathlib import Path

from backup_tool.mssql.udl import udl_to_fields


def test_udl_to_fields(tmp_path: Path) -> None:
    path = tmp_path / "test.udl"
    content = "[oledb]\n;Everything after this line is an OLE DB initstring\nProvider=SQLOLEDB;Data Source=SERVER01;Initial Catalog=ERP;User ID=sa;Password=secret;\n"
    path.write_text(content, encoding="utf-16")
    fields = udl_to_fields(path)
    assert fields["host"] == "SERVER01"
    assert fields["database"] == "ERP"
    assert fields["username"] == "sa"
    assert fields["password"] == "secret"

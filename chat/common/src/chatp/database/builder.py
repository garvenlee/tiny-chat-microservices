from glob import glob
from os.path import basename
from typing import Optional, Sequence


# legacy
def build_create_query(
    table: str,
    *,
    columns: tuple[str],
    on_conflict_target: Optional[tuple[str]] = None,
    on_conflict_action: Optional[dict] = None,  # set field=val, ...
    returning: Optional[tuple[str]] = None,
    where_fields: Optional[tuple[str]] = None,  # select .. where key=val and ...
):
    num_columns = len(columns)
    values_placeholder = ", ".join(
        f"${bind_idx}" for bind_idx in range(1, 1 + num_columns)
    )
    if on_conflict_target is not None:
        target = ", ".join(on_conflict_target)
        if on_conflict_action is not None:  # TODO make this bind args
            action_fields = ", ".join(
                f"{name}={val}" for name, val in on_conflict_action.items()
            )
            action = f"UPDATE SET {action_fields}"
        else:
            action = "NOTHING"

        if returning is not None:  # query_where_fields is a bind args
            returning = ", ".join(returning)
            if where_fields is None:
                raise RuntimeError(
                    "`query_where_fields` must not be None when `on_confilct_target` and `returning` given"
                )

            index_map = {field: idx for idx, field in enumerate(columns, 1)}
            where_placeholder = [None] * len(where_fields)
            for idx, field in enumerate(where_fields):
                if (placeholder := index_map.get(field)) is not None:
                    where_placeholder[idx] = placeholder
                else:
                    num_columns += 1
                    where_placeholder[idx] = num_columns
            where = " and ".join(
                f"{field}=${placeholder}"
                for field, placeholder in zip(where_fields, where_placeholder)
            )
            sql = (
                f"WITH ins AS(INSERT INTO {table}({', '.join(columns)}) VALUES({values_placeholder}) "
                f"ON CONFLICT({target}) DO {action} RETURNING {returning}) "
                f"SELECT {returning} FROM ins UNION ALL SELECT {returning} FROM {table} WHERE {where} LIMIT 1;"
            )
        else:
            sql = (
                f"INSERT INTO {table}({', '.join(columns)}) VALUES({values_placeholder}) "
                f"ON CONFLICT({target}) DO {action};"
            )
    else:
        if returning is not None:
            returning = ", ".join(returning)
            sql = f"INSERT INTO {table}({', '.join(columns)}) VALUES({values_placeholder} returning {returning}"
        else:
            sql = (
                f"INSERT INTO {table}({', '.join(columns)}) VALUES({values_placeholder}"
            )
    return sql


def build_read_query(table: str, *, columns: tuple[str], where_fields: tuple[str]):
    where = " and ".join(
        f"{field}=${placeholder}" for field, placeholder in enumerate(where_fields, 1)
    )
    return f'SELECT {", ".join(columns)} FROM {table} WHERE {where};'  # stmt, can be cached


def build_update_query(
    table: str,
    *,
    columns: tuple[str],
    values: tuple[str],
    where_fields: tuple[str],
):
    # here, bind stmt with update_field
    update_field = ", ".join(
        f"{field}='{value}'" for field, value in zip(columns, values)
    )
    where = " and ".join(
        f"{field}=${placeholder}" for field, placeholder in enumerate(where_fields, 1)
    )
    return f"UPDATE {table} SET {update_field} WHERE {where};"


def query_builder() -> Sequence[tuple[str, str]]:
    register_user = build_create_query(
        table="users",
        columns=("email", "password", "created_at"),
        returning=("uid", "confirmed"),
        on_conflict_target=("email",),  # DO NOTHING
        query_where_fields=("email",),
    )

    login_user = build_read_query(
        table="users",
        columns=("uid", "password", "confirmed"),
        where_fields=("email",),
    )

    query_user = build_read_query(
        table="users",
        columns=("uid", "confirmed"),
        where_fields=("email",),
    )

    confirm_user = build_update_query(
        table="users",
        columns=("confirmed",),
        values=(True,),
        where_fields=("uid",),
    )

    return (
        ("register_user", register_user),
        ("login_user", login_user),
        ("query_user", query_user),
        ("cconfirm_user", confirm_user),
    )


def load_file(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def schema_builder(file_pattern: str) -> Sequence[tuple[str, str]]:
    for path in glob(file_pattern):
        name = basename(path)[:-4]
        yield name, load_file(path)


def query_builder(file_pattern: str) -> dict[str, str]:
    return dict(schema_builder(file_pattern))

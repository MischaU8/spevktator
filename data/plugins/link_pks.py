from datasette import hookimpl
import markupsafe
import re

POST_ID_RE = re.compile(r"^-\d+_\d+$")


@hookimpl
def render_cell(value, column, table, database):
    "make any id value that looks like a post id a link to /posts/id"
    if not isinstance(value, str):
        return None
    if database != "vk":
        return None
    if column == "id" and POST_ID_RE.match(value):
        href = "/vk/posts/" + value
        return markupsafe.Markup(
            '<a href="{href}">{value}</a>'.format(
                href=markupsafe.escape(href),
                value=markupsafe.escape(value or "") or "&nbsp;",
            )
        )

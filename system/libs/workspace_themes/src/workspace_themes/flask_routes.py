import hashlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Final, assert_never

from flask import Flask, Response, abort, request, send_file
from loguru import logger

from workspace_themes.catalog import CachingThemeCatalogLoader
from workspace_themes.contract import (
    BUNDLE_FILE_NAME,
    INJECTED_APP_HEADER,
    INJECTED_LAYER_ORDER,
    INJECTED_ROUTE_PREFIX,
)
from workspace_themes.data_types import ThemeCatalog
from workspace_themes.errors import ThemeFileNotFoundError
from workspace_themes.injection import (
    INJECTED_BASE_FILE_NAME,
    INJECTED_KIT_FILE_NAME,
    INJECTED_LAYERS_FILE_NAME,
    injected_kit_script,
    parse_theme_level,
    resolve_injected_theme_asset,
    style_text_at_level,
)
from workspace_themes.primitives import ThemeLevel
from workspace_themes.serving import (
    CSS_MIMETYPE,
    THEME_STATIC_ROUTE_PREFIX,
    ThemeAsset,
    ThemeBundle,
    ThemeFile,
    ThemeStyleFile,
    resolve_theme_asset,
    theme_file_security_headers,
)

# Every theme answer is revalidated on each use, so an edited theme shows on the next load (section 5.1).
_CACHE_CONTROL: Final[str] = "no-cache"
_ENDPOINT: Final[str] = "workspace_theme_static"
_ETAG_LENGTH: Final[int] = 16


def _etag_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_ETAG_LENGTH]


def _theme_asset_response(asset: ThemeAsset) -> Response:
    match asset:
        case ThemeFile(path=path):
            response = send_file(path, conditional=True, max_age=0)
            response.headers.update(theme_file_security_headers(path))
        case ThemeBundle(css=css):
            response = Response(css, mimetype=CSS_MIMETYPE)
            response.headers.update(
                theme_file_security_headers(PurePosixPath(BUNDLE_FILE_NAME))
            )
            # Tagged by its own text: which app overlays it imports follows the apps the workspace has, which the
            # theme's revision does not cover.
            response.set_etag(_etag_of(css))
            response.make_conditional(request)
        case ThemeStyleFile(path=path, css=css):
            response = Response(css, mimetype=CSS_MIMETYPE)
            response.headers.update(theme_file_security_headers(path))
            response.set_etag(_etag_of(css))
            response.make_conditional(request)
        case _ as unreachable:
            assert_never(unreachable)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return response


def serve_theme_static(
    load_catalog: Callable[[], ThemeCatalog], asset_path: str
) -> Response:
    """The answer to ``GET /_static/themes/<asset_path>``: the file, or 404."""
    try:
        asset = resolve_theme_asset(load_catalog(), asset_path)
    except ThemeFileNotFoundError as error:
        logger.debug("No theme file for {}: {}", asset_path, error)
        abort(404)
    return _theme_asset_response(asset)


def _text_response(text: str, mimetype: str, file_name: str) -> Response:
    response = Response(text, mimetype=mimetype)
    response.headers.update(theme_file_security_headers(PurePosixPath(file_name)))
    response.headers["Cache-Control"] = _CACHE_CONTROL
    response.set_etag(_etag_of(text))
    response.make_conditional(request)
    return response


def _request_level() -> ThemeLevel:
    try:
        return parse_theme_level(request.args.get("level"))
    except ThemeFileNotFoundError as error:
        logger.debug("No injected theme file for {}: {}", request.path, error)
        abort(404)


def register_injected_theme_routes(
    application: Flask,
    load_catalog: Callable[[], ThemeCatalog],
    read_kit_script: Callable[[], str],
    read_kit_stylesheet: Callable[[], str],
    level_of_app: Callable[[str | None], ThemeLevel],
) -> None:
    """Serve ``/__workspace_theme/``: what an app's page needs when the theme is put into it from outside.

    The proxy in front of the app puts ``layers.css`` and ``kit.js`` at the top of each page and sends this prefix
    here, naming the app in ``X-Mngr-Forward-Service``; ``level_of_app`` gives that app's theme level, which ``kit.js``
    carries and every theme file the kit asks for names in its ``level`` query. At none both are empty, so a page
    that themes itself keeps its own layer order.
    """

    def layers() -> Response:
        level = level_of_app(request.headers.get(INJECTED_APP_HEADER))
        return _text_response(
            "" if level == ThemeLevel.NONE else INJECTED_LAYER_ORDER,
            CSS_MIMETYPE,
            INJECTED_LAYERS_FILE_NAME,
        )

    def kit() -> Response:
        level = level_of_app(request.headers.get(INJECTED_APP_HEADER))
        return _text_response(
            injected_kit_script(read_kit_script(), level),
            "text/javascript",
            INJECTED_KIT_FILE_NAME,
        )

    def base() -> Response:
        level = _request_level()
        return _text_response(
            style_text_at_level(read_kit_stylesheet(), level),
            CSS_MIMETYPE,
            INJECTED_BASE_FILE_NAME,
        )

    def themes(asset_path: str) -> Response:
        level = _request_level()
        try:
            asset = resolve_injected_theme_asset(load_catalog(), asset_path, level)
        except ThemeFileNotFoundError as error:
            logger.debug("No injected theme file for {}: {}", asset_path, error)
            abort(404)
        return _theme_asset_response(asset)

    for name, view in (
        (INJECTED_LAYERS_FILE_NAME, layers),
        (INJECTED_KIT_FILE_NAME, kit),
        (INJECTED_BASE_FILE_NAME, base),
    ):
        application.add_url_rule(
            f"{INJECTED_ROUTE_PREFIX}{name}",
            endpoint=f"workspace_injected_{name}",
            view_func=view,
            methods=["GET"],
        )
    application.add_url_rule(
        f"{INJECTED_ROUTE_PREFIX}themes/<path:asset_path>",
        endpoint="workspace_injected_themes",
        view_func=themes,
        methods=["GET"],
    )


def register_theme_static_route(
    application: Flask, load_catalog: Callable[[], ThemeCatalog]
) -> None:
    """Serve ``/_static/themes/<path>`` from this app's own origin: the theme bundles and the files they load."""
    application.add_url_rule(
        f"{THEME_STATIC_ROUTE_PREFIX}<path:asset_path>",
        endpoint=_ENDPOINT,
        view_func=lambda asset_path: serve_theme_static(load_catalog, asset_path),
        methods=["GET"],
    )


def register_workspace_theme_route(application: Flask) -> None:
    """Serve the workspace's themes from this app's origin, reading them from the working directory, which is the
    repo root every supervised app runs from."""
    loader = CachingThemeCatalogLoader(repo_root=Path.cwd())
    register_theme_static_route(application, loader.load)

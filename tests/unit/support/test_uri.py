"""Verify immutable URI construction and query data behavior.

The tests exercise Python URI types and Titanspan's nested-data utilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest

from titanspan.contracts import HtmlRenderable
from titanspan.contracts.routing import UriUrlGenerator as RoutingUrlGenerator
from titanspan.http.response_factory import NativeResponseFactory
from titanspan.support import (
    Stringable,
    Uri,
    UriContextError,
    UriQueryString,
    UriUrlGenerator,
)
from titanspan.support.uri import bind_uri_services

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


_HTTPS_DEFAULT_PORT = 443
_PERMANENT_REDIRECT_STATUS = 301
_DEFAULT_REDIRECT_STATUS = 302
_URI_TEST_PORT = 8080
_URI_UPDATED_PORT = 8443
_MAX_URI_PORT = 65535


@pytest.mark.unit
def test_uri_exposes_components_and_preserves_the_original_value() -> None:
    """Read URI components while returning a normalized network origin.

    Returns:
        None.
    """
    original = (
        "https://service:secret@EXAMPLE.com:443/"  # pragma: allowlist secret
        "docs/installation"
        "?version=1#intro"
    )
    uri = Uri.of(original)

    assert uri.scheme() == "https"
    assert uri.authority() == "service:secret@EXAMPLE.com:443"
    assert uri.user() == "service"
    assert uri.user(with_password=True) == "service:secret"
    assert uri.password() == "secret"
    assert uri.host() == "example.com"
    assert uri.port() == _HTTPS_DEFAULT_PORT
    assert uri.origin() == "https://example.com"
    assert uri.path() == "docs/installation"
    assert uri.path_segments() == ("docs", "installation")
    assert uri.fragment() == "intro"
    assert uri.value() == original
    assert str(uri) == original
    assert Uri("https://example.com/").password() is None
    assert repr(Uri("https://example.com/")) == "Uri('https://example.com/')"


@pytest.mark.unit
def test_uri_origin_handles_default_ports_and_opaque_addresses() -> None:
    """Normalize origins and omit origins for non-hierarchical URIs.

    Returns:
        None.
    """
    assert Uri.of("http://Example.test:80/path").origin() == (
        "http://example.test"
    )
    assert Uri.of("https://[2001:db8::1]:443/path").origin() == (
        "https://[2001:db8::1]"
    )
    assert Uri.of("wss://example.test:8080/socket").origin() == (
        "wss://example.test:8080"
    )
    assert Uri.of("mailto:user@example.test").origin() is None
    assert Uri.of("/relative/path").origin() is None
    assert Uri.of("file:///etc/hosts").origin() is None


@pytest.mark.unit
def test_uri_transformations_are_immutable_and_keep_query_components() -> None:
    """Return new URI values for component changes without mutating input.

    Returns:
        None.
    """
    original = Uri.of("https://example.test/a?keep=1#old")
    changed = (
        original.with_scheme("http")
        .with_user("alice", "p@ss")
        .with_host("api.example.test")
        .with_port(8080)
        .with_path("v2/items")
        .with_fragment("new")
    )

    assert changed.value() == (
        "http://alice:p%40ss@api.example.test"  # pragma: allowlist secret
        ":8080/v2/items?keep=1#new"
    )
    assert original.value() == "https://example.test/a?keep=1#old"
    assert changed.with_user(None).user() is None
    assert changed.with_port(None).port() is None
    assert changed.without_fragment().fragment() is None
    assert changed.without_fragment().value().endswith("?keep=1")
    assert changed.with_host("[2001:db8::2]").host() == "2001:db8::2"
    assert (
        Uri.of("https://[2001:db8::1]:8080").with_host("2001:db8::2").port()
        == _URI_TEST_PORT
    )
    assert (
        Uri.of("https://[2001:db8::1]:8080").with_port(_URI_UPDATED_PORT).port()
        == _URI_UPDATED_PORT
    )
    assert changed.with_path("/already-rooted").path() == "already-rooted"


@pytest.mark.unit
def test_uri_user_info_encodes_colons_in_usernames() -> None:
    """Keep username colons separate from the password delimiter.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test").with_user(
        "alice:admin",
        "secret:two",
    )

    assert uri.user() == "alice:admin"
    assert uri.password() == "secret:two"
    assert uri.value() == ("https://alice%3Aadmin:secret:two@example.test")


@pytest.mark.unit
def test_uri_parses_nested_query_values_and_preserves_duplicate_keys() -> None:
    """Parse bracket notation, empty values, and repeated query parameters.

    Returns:
        None.
    """
    uri = Uri.of(
        "https://example.test/?filter[name]=Ada&tags[]=async"
        "&tags[]=ai&flag&filter[name]=Grace"
    )

    assert uri.query().all() == {
        "filter": {"name": ["Ada", "Grace"]},
        "tags": ["async", "ai"],
        "flag": "",
    }
    assert uri.query().get("filter.name") == ["Ada", "Grace"]
    assert uri.query().get("missing", "fallback") == "fallback"
    assert uri.query().all(["filter.name", "flag"]) == {
        "filter": {"name": ["Ada", "Grace"]},
        "flag": "",
    }
    assert isinstance(uri.query(), UriQueryString)
    assert uri.query().decode() == (
        "filter[name]=Ada&tags[]=async&tags[]=ai&flag&filter[name]=Grace"
    )


@pytest.mark.unit
def test_uri_query_changes_merge_replace_push_and_remove_nested_values() -> (
    None
):
    """Merge query data while preserving nested and list semantics.

    Returns:
        None.
    """
    original = Uri.of("https://example.test/?filter[name]=Ada&tags[]=python")
    merged = original.with_query({"filter.role": "admin", "page": 2})

    assert merged.query().decode() == (
        "filter[name]=Ada&filter[role]=admin&tags[0]=python&page=2"
    )
    assert merged.with_query_if_missing(
        {"filter.name": "Grace", "locale": "en"}
    ).query().all() == {
        "filter": {"name": "Ada", "role": "admin"},
        "page": "2",
        "tags": ["python"],
        "locale": "en",
    }
    assert merged.push_onto_query("tags", "ai").query().all()["tags"] == [
        "python",
        "ai",
    ]
    assert merged.without_query("filter.role").query().all() == {
        "page": "2",
        "tags": ["python"],
        "filter": {"name": "Ada"},
    }
    assert merged.replace_query({"only": "new"}).query().decode() == (
        "only=new"
    )
    assert original.query().all() == {
        "filter": {"name": "Ada"},
        "tags": ["python"],
    }


@pytest.mark.unit
def test_uri_decode_and_html_adapters_only_change_query_escaping() -> None:
    """Decode percent-encoded queries and expose expected string adapters.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test/a%20b?q=hello%20world#kept")

    assert uri.decode() == ("https://example.test/a%20b?q=hello world#kept")
    assert uri.to_html() == uri.value()
    assert uri.to_html() == uri.value()
    assert uri.to_stringable().to_string() == uri.value()
    assert uri.to_stringable().to_string() == uri.value()
    assert uri.is_empty() is False
    assert uri.is_empty() is False
    assert Uri.of("  ").is_empty()
    assert Uri.of("  ").is_empty()
    assert Uri.of("  ").is_not_empty() is False
    assert Uri.of("  ").is_not_empty() is False
    uri_with_credentials = Uri.of(
        "https://alice:secret@example.test"  # pragma: allowlist secret
    )
    assert repr(uri_with_credentials) == "Uri('https://example.test')"


@pytest.mark.unit
def test_uri_redirects_with_status_and_headers() -> None:
    """Create a native redirect response from a local URI value.

    Returns:
        None.
    """
    with bind_uri_services(
        None,
        NativeResponseFactory,
    ):
        response = Uri.of("/done").redirect(
            301,
            {"X-Redirect-Reason": "complete"},
        )

    assert response.status_code == _PERMANENT_REDIRECT_STATUS
    assert response.headers["location"] == "/done"
    assert response.headers["x-redirect-reason"] == "complete"


@pytest.mark.unit
def test_uri_resolver_supports_url_generation_helpers() -> None:
    """Resolve conventional URL builders through the configured callback.

    Returns:
        None.
    """

    class UrlBuilder:
        """Provide deterministic route generation for resolver tests.

        The instance records arguments so tests can verify forwarding
        behaviour without requiring a configured application router.
        """

        def __init__(self) -> None:
            """Create an empty trace of forwarded generator arguments.

            The trace is local to this test instance and has no shared state.
            """
            self.calls: list[tuple[object, ...]] = []

        def to(self, path: str) -> str:
            """Build an absolute path URL.

            Args:
                path: The path passed to the generator.

            Returns:
                A test URL.
            """
            self.calls.append(("to", path))
            return "https://example.test/to"

        def route(
            self,
            name: str,
            parameters: Mapping[str, object],
            absolute: bool,
        ) -> str:
            """Build a route URL.

            Args:
                name: The route name.
                parameters: Route parameters.
                absolute: Whether the URL should be absolute.

            Returns:
                A test URL.
            """
            self.calls.append(("route", name, parameters, absolute))
            return f"https://example.test/routes/{name}"

        def signed_route(
            self,
            name: str,
            parameters: Mapping[str, object],
            expiration: object,
            absolute: bool,
        ) -> str:
            """Build a signed route URL.

            Args:
                name: The route name.
                parameters: Route parameters.
                expiration: The requested expiration value.
                absolute: Whether the URL should be absolute.

            Returns:
                A test URL.
            """
            self.calls.append(
                ("signed_route", name, parameters, expiration, absolute)
            )
            return f"https://example.test/signed/{name}"

        def action(
            self,
            action: str | Sequence[str],
            parameters: Mapping[str, object],
            absolute: bool,
        ) -> str:
            """Build a controller action URL.

            Args:
                action: The controller action.
                parameters: Action parameters.
                absolute: Whether the URL should be absolute.

            Returns:
                A test URL.
            """
            self.calls.append(("action", action, parameters, absolute))
            return f"https://example.test/actions/{action}"

    builder = UrlBuilder()
    with bind_uri_services(
        lambda: builder,
        NativeResponseFactory,
    ):
        assert Uri.to("/docs").value() == "https://example.test/to"
        assert Uri.route("home").value() == "https://example.test/routes/home"
        assert Uri.signed_route("home").value() == (
            "https://example.test/signed/home"
        )
        assert Uri.signed_route("home").value() == (
            "https://example.test/signed/home"
        )
        assert Uri.temporary_signed_route("home", 60).value() == (
            "https://example.test/signed/home"
        )
        assert Uri.temporary_signed_route("home", 60).value() == (
            "https://example.test/signed/home"
        )
        assert Uri.action("HomeController@index").value() == (
            "https://example.test/actions/HomeController@index"
        )
        assert builder.calls == [
            ("to", "/docs"),
            ("route", "home", {}, False),
            ("signed_route", "home", {}, None, False),
            ("signed_route", "home", {}, None, False),
            ("signed_route", "home", {}, 60, False),
            ("signed_route", "home", {}, 60, False),
            ("action", "HomeController@index", {}, False),
        ]


@pytest.mark.unit
def test_uri_query_uses_rfc3986_decoding_and_preserves_literal_plus() -> None:
    """Decode percent escapes without form-style plus conversion.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test/?search=a+b%20c&flag")

    assert uri.query().get("search") == "a+b c"
    assert uri.query().get("flag") == ""
    assert uri.query().decode() == "search=a+b c&flag"


@pytest.mark.unit
def test_uri_query_parses_nested_and_sparse_numeric_keys() -> None:
    """Keep sparse numeric query indexes as mapping keys.

    Returns:
        None.
    """
    query = Uri.of(
        "https://example.test/?list[9]=nine&list[10]=ten&list[01]=leading"
        "&list[9223372036854775808]=out%20of%20range"
        "&zero[0]=first&negative[-1]=prior"
        "&list[\u0661]=unicode&duplicate=one&duplicate=two&duplicate=three"
        "&x=scalar&x[name]=nested&[root]=literal&bad[key]tail[end]=value"
    ).query()

    assert query.all() == {
        "list": {
            9: "nine",
            10: "ten",
            "01": "leading",
            "9223372036854775808": "out of range",
            "\u0661": "unicode",
        },
        "zero": ["first"],
        "negative": {-1: "prior"},
        "duplicate": ["one", "two", "three"],
        "x": {"name": "nested"},
        "[root]": "literal",
        "bad[key]tail[end]": "value",
    }
    assert query.get("duplicate") == ["one", "two", "three"]
    assert query.get("x") == {"name": "nested"}
    assert query.get("[root]") == "literal"
    assert query.get("bad[key]tail[end]") == "value"


@pytest.mark.unit
def test_uri_query_preserves_numeric_keys_at_the_root() -> None:
    """Keep top-level numeric query keys in the public mapping.

    Returns:
        None.
    """
    query = Uri.of("https://example.test/?0=first&1=second").query()

    assert query.all() == {0: "first", 1: "second"}


@pytest.mark.unit
def test_uri_query_all_can_select_multiple_nested_paths() -> None:
    """Select multiple paths without changing the parsed source data.

    Returns:
        None.
    """
    query = Uri.of(
        "https://example.test/?user[name]=Ada&user[role]=admin&active=1"
    ).query()

    assert query.all(["user.name", "active"]) == {
        "user": {"name": "Ada"},
        "active": "1",
    }
    assert query.all([]) == {
        "user": {"name": "Ada", "role": "admin"},
        "active": "1",
    }
    assert query.all("") == {
        "user": {"name": "Ada", "role": "admin"},
        "active": "1",
    }


@pytest.mark.unit
def test_uri_query_if_missing_treats_wildcard_characters_literally() -> None:
    """Treat asterisk characters as key text rather than path wildcards.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test/?role=user&tenant=10")

    updated = uri.with_query_if_missing({"*": "admin"})

    assert updated.query().all() == {
        "role": "user",
        "tenant": "10",
        "*": "admin",
    }


@pytest.mark.unit
def test_uri_rejects_invalid_ports_during_construction() -> None:
    """Reject malformed authorities when the URI is created.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="Port could not be cast"):
        Uri.of("https://example.test:not-a-port")


@pytest.mark.unit
def test_uri_port_range_and_authority_less_paths() -> None:
    """Update the port independently and reject invalid integer values.

    Returns:
        None.
    """
    with_port = Uri.of("/path").with_port(_URI_TEST_PORT)

    assert with_port.value() == "//:8080/path"
    assert with_port.port() == _URI_TEST_PORT
    assert with_port.with_port(None).value() == "/path"
    assert (
        Uri.of("https://example.test").with_port(_MAX_URI_PORT).port()
        == _MAX_URI_PORT
    )

    with pytest.raises(ValueError, match="between 0 and 65535"):
        Uri.of("https://example.test").with_port(_MAX_URI_PORT + 1)
    with pytest.raises(ValueError, match="between 0 and 65535"):
        Uri.of("https://example.test").with_port(True)


@pytest.mark.unit
def test_uri_construction_accepts_python_and_fluent_string_values() -> None:
    """Accept urllib results and the framework's Stringable adapter.

    Returns:
        None.
    """
    parsed = urlsplit("https://example.test/parsed")

    assert Uri(parsed).value() == "https://example.test/parsed"
    assert Uri(Stringable("https://example.test/stringable")).value() == (
        "https://example.test/stringable"
    )


@pytest.mark.unit
def test_uri_parses_nested_query_values() -> None:
    """Parse bracketed query arrays while preserving dotted literal keys.

    Returns:
        None.
    """
    uri = Uri.of(
        "https://example.test/users?key_1=value"
        "&key_2[sub_field]=value&key_3[]=value"
        "&key_4[9]=value&key_5[][][foo][9]=bar"
        "&key.6=value&flag_value"
    )

    assert uri.query().all() == {
        "key_1": "value",
        "key_2": {"sub_field": "value"},
        "key_3": ["value"],
        "key_4": {9: "value"},
        "key_5": [[{"foo": {9: "bar"}}]],
        "key.6": "value",
        "flag_value": "",
    }


@pytest.mark.unit
def test_uri_builder_preserves_query_composition_rules() -> None:
    """Build nested query values and preserve merge and replacement rules.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test").with_query(
        {
            "name": "James",
            "age": 38,
            "role": {"title": "Developer", "focus": "Python"},
            "tags": ["person", "employee"],
            "flag": "",
        }
    )

    assert uri.query().decode() == (
        "name=James&age=38&role[title]=Developer&role[focus]=Python"
        "&tags[0]=person&tags[1]=employee&flag="
    )
    assert uri.without_query(["name"]).query().decode() == (
        "age=38&role[title]=Developer&role[focus]=Python"
        "&tags[0]=person&tags[1]=employee&flag="
    )
    assert uri.replace_query({"name": "James"}).query().decode() == (
        "name=James"
    )
    assert Uri.of("https://example.test").with_query({}).value() == (
        "https://example.test"
    )


@pytest.mark.unit
def test_uri_exposes_path_segments_and_framework_interop_protocols() -> None:
    """Expose stable path segments and both supported HTML contracts.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test/one/two/three/?foo=bar#section")

    assert uri.path_segments() == ("one", "two", "three")
    assert uri.path_segments() == ("one", "two", "three")
    assert isinstance(uri, HtmlRenderable)
    assert uri.to_html() == uri.to_html() == uri.value()
    assert uri.to_string() == uri.to_string() == uri.value()
    assert uri.get_uri().path == "/one/two/three/"


@pytest.mark.unit
def test_uri_preserves_empty_delimiters_and_decodes_query_only() -> None:
    """Keep empty query and fragment delimiters in the original value.

    Returns:
        None.
    """
    original = Uri.of("https://example.test/path?#")

    assert original.value() == "https://example.test/path?#"
    assert original.without_fragment().value() == "https://example.test/path?"
    assert original.without_query("missing").value() == (
        "https://example.test/path#"
    )
    assert (
        Uri.of("https://example.test/path?#fragment").with_path("/new").value()
        == "https://example.test/new?#fragment"
    )
    assert Uri.of("https://example.test/?x=a%2Bb").decode() == (
        "https://example.test/?x=a+b"
    )
    assert Uri.of("https://example.test/path").decode() == (
        "https://example.test/path"
    )


@pytest.mark.unit
def test_uri_uses_conditionable_tappable_and_explicit_macros() -> None:
    """Reuse Support mixins without dynamic method lookup or hidden mutation.

    Returns:
        None.
    """
    uri = Uri.of("https://example.test/original")
    seen: list[str] = []

    selected = uri.when(
        True,
        lambda current, _condition: current.with_path("updated"),
    )
    assert isinstance(selected, Uri)
    changed = selected
    tapped = changed.tap(lambda current: seen.append(current.path()))

    def with_test_path(current: Uri) -> Uri:
        """Return a URI with the macro-specific path.

        Args:
            current: The URI supplied to the macro invocation.

        Returns:
            The changed URI value.
        """
        return current.with_path("macro")

    Uri.flush_macros()
    Uri.macro("with_test_path", with_test_path)
    try:
        macro_result = Uri.of("https://example.test").call_macro(
            "with_test_path"
        )
        assert Uri.has_macro("with_test_path")
    finally:
        Uri.flush_macros()

    assert isinstance(changed, Uri)
    assert tapped is changed
    assert seen == ["updated"]
    assert isinstance(macro_result, Uri)
    assert macro_result.path() == "macro"


@pytest.mark.unit
def test_uri_requires_a_context_local_url_generator_for_route_factories() -> (
    None
):
    """Raise a clear error when route generation is not configured.

    Returns:
        None.
    """
    with pytest.raises(UriContextError, match="active application context"):
        Uri.to("/home")


@pytest.mark.unit
def test_uri_url_generator_is_reexported_from_canonical_contract() -> None:
    """Keep the Support import identical to the routing contract object.

    Re-exporting preserves one structural contract identity in the framework.
    """
    assert UriUrlGenerator is RoutingUrlGenerator


@pytest.mark.unit
def test_uri_parsing_does_not_require_an_application_context() -> None:
    """Keep ordinary URI construction usable without routing services.

    Only factories that resolve application services require active context.
    """
    uri = Uri.of("https://example.test/docs?version=2#overview")

    assert uri.host() == "example.test"
    assert uri.query().get("version") == "2"
    assert uri.fragment() == "overview"


@pytest.mark.unit
def test_uri_query_adapter_exposes_python_string_methods() -> None:
    """Expose encoded and decoded query strings through Python methods.

    Returns:
        None.
    """
    query = UriQueryString(Uri("https://example.test/?lang=en&empty="))

    assert str(query) == "lang=en&empty="
    assert query.value() == "lang=en&empty="
    assert query.decode() == "lang=en&empty="
    assert query.get() == {"lang": "en", "empty": ""}
    assert query.all("lang") == {"lang": "en"}
    assert query.all() == {"lang": "en", "empty": ""}


@pytest.mark.unit
def test_uri_redirect_uses_the_current_value() -> None:
    """Return a native redirect for the current local URI value.

    Returns:
        None.
    """
    uri = Uri("/next?source=docs")

    with bind_uri_services(
        None,
        NativeResponseFactory,
    ):
        direct = uri.redirect()
    assert direct.status_code == _DEFAULT_REDIRECT_STATUS
    assert direct.headers["location"] == uri.value()


@pytest.mark.unit
def test_uri_dump_writes_a_readable_value_and_returns_self(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Write the string and extra values while preserving fluent identity.

    Args:
        capsys: Pytest's captured standard-output fixture.

    Returns:
        None.
    """
    uri = Uri("https://example.test/guide")

    assert uri.dump("inspected") is uri
    assert capsys.readouterr().out == (
        "'https://example.test/guide'\n'inspected'\n"
    )


@pytest.mark.unit
def test_uri_query_mutation_operations() -> None:
    """Update query keys and URI components through immutable operations.

    Returns:
        None.
    """
    uri = Uri("https://example.test/?existing=1")

    assert (
        uri.with_query_if_missing({"existing": "3"}).query().get("existing")
        == "1"
    )
    assert uri.push_onto_query("existing", "2").query().get("existing") == [
        "1",
        "2",
    ]
    assert uri.without_query("existing").query().all() == {}
    assert uri.replace_query({"only": "value"}).query().all() == {
        "only": "value"
    }
    assert uri.with_fragment("section").without_fragment().fragment() is None


@pytest.mark.unit
def test_uri_push_handles_missing_scalars_maps_and_duplicate_items() -> None:
    """Append URI query values for each supported current-value shape.

    Returns:
        None.
    """
    uri = Uri("https://example.test/?tag=one&filter[name]=Ada&tags[]=first")

    assert uri.push_onto_query("tag", "two").query().get("tag") == [
        "one",
        "two",
    ]
    assert uri.push_onto_query("new", "value").query().get("new") == ["value"]
    assert uri.push_onto_query(
        "filter",
        ["admin", "admin"],
    ).query().get("filter") == {
        "name": "Ada",
        0: "admin",
        1: "admin",
    }
    assert uri.push_onto_query(
        "tags",
        ["first", "second", "second"],
    ).query().get("tags") == ["first", "second"]

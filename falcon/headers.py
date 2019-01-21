"""
Class for HTTP Headers, used by :class:`falcon.Response`
"""

from collections import defaultdict
from functools import partial

import six

from falcon.response_helpers import (format_content_disposition,
                                     format_etag_header, format_range)
from falcon.util import TimezoneGMT, dt_to_http
from falcon.util.uri import encode as uri_encode
from falcon.util.uri import encode_value as uri_encode_value


def header_property(name, doc, transform=None):
    """Create a header getter/setter.

    Args:
        name: Header name, e.g., "Content-Type"
        doc: Docstring for the property
        transform: Transformation function to use when setting the
            property. The value will be passed to the function, and
            the function should return the transformed value to use
            as the value of the header (default ``None``).

    """
    normalized_name = name.lower()

    def fget(self):
        return self.get(normalized_name)

    if transform is None:
        def fset(self, value):
            # NOTE(nateyo): Deleting on value=None seems strange...
            if value is None:
                try:
                    del self._headers[normalized_name]
                except KeyError:
                    pass
            else:
                self.add(normalized_name, str(value))
    else:
        def fset(self, value):
            if value is None:
                try:
                    del self._headers[normalized_name]
                except KeyError:
                    pass
            else:
                self.add(normalized_name, transform(value))

    def fdel(self):
        self.remove(normalized_name)

    return property(fget, fset, fdel, doc)


if six.PY2:
    def BASE_NORMALIZER(sep, data):
        """
        Default normalizer for :class:`Headers`.

        Args:
            sep (str): Character to join header items with
            data (list): List of particular header items

        Returns:
            str: A string representation of the header value.
        """
        return str(sep.join(data))
else:
    def BASE_NORMALIZER(sep, data):
        """
        Default normalizer for :class:`Headers`.

        Args:
            sep (str): Character to join header items with
            data (list): List of particular header items

        Returns:
            str: A string representation of the header value.
        """
        return sep.join(data)


COMMA_NORMALIZER = partial(BASE_NORMALIZER, sep=",")
SEMICOLON_NORMALIZER = partial(BASE_NORMALIZER, sep=";")


class Headers(object):
    """
    Represents HTTP headers for :class:`Response`. All headers
    are stored in a :type:`dict` with a case-insensitive key. The value of
    the dictionary entry will always be a list.

    Normalizers can be provided when calling :meth:`add` that will be called
    when the headers are exported to strs.
    """

    def __init__(self):
        self._headers = defaultdict(list)
        self._normalizers = {}

    def copy(self):
        """
        Return a copy of all the headers

        Returns:
            dict: Headers dictionary
        """
        return self._headers.copy()

    def exists(self, name):
        """
        Check if a header exists.

        Args:
            name (str): Header name, case-insensitive.

        Returns:
            bool: ``True`` if the header exists, ``False`` otherwise.
        """
        return name.lower() in self._headers

    def add(self, name, value, normalizer=COMMA_NORMALIZER):
        """
        Add a header to the dictionary. Note that if 'name' already
        exists as a header, calling add will overwrite the existing data.

        Args:
            name (str): Header name, case-insensitive
            value (list or str): Header items, if :type:`str`, will be added to single item list
            normalizer (func, optional): Normalizer to be executed on header export. (Defaults to ``COMMA_NORMALIZER``)
        """
        name = name.lower()
        self._headers[name] = value if type(value) is list else [value]
        self._normalizers[name] = normalizer

    def append(self, name, value):
        """
        Append a value to an existing header. If the header does not
        currently exist in ``_headers``, the key will be created and appended.

        Args:
            name (str): Header name, case-insensitive
            value (str): Header value to append
        Raises:
            KeyError: If no existing header is found by the given name
        """
        # TODO(nateyo): Since defaultdict, normalizer might not be created for
        #              for a given header.
        self._headers[name.lower()].append(value)

    def set_normalizer(self, name, normalizer):
        """
        Sets the normalizer for an existing header. This will
        set the normalizer for this header, regardless if the header
        exists in ``_headers`` or not.

        Args:
            name (str): Header name, case-insensitive.
            normalizer (func): Normalizer to be executed on header export.
        """
        self._normalizers[name.lower()] = normalizer

    def get(self, name, use_normalizer=True):
        """
        Retrieve a header from the dictionary. If `use_normalizer` is `False`,
        retrieves the list associated with the header `name`. If `use_normalizer`
        is set to `True`, a ``str`` will be returned.

        Args:
            name (str): Header name, case-insensitive
            use_normalizer (bool): If `True` normalizes the header value, if `False`
                                   performs no normalization. Defaults to `True`
        Returns:
            ``str`` OR ``list``: Either a normalized ``str`` or raw ``list``.
        """
        # NOTE(nateyo): Maybe having this return either a list or a str is bad.
        # NOTE(nateyo): Open to comments on normalizer existence and errors

        name = name.lower()
        if use_normalizer:
            return self._normalizers[name](self._headers[name])

        return self._headers[name]

    def remove(self, name):
        """
        Remove an existing header. If the header does not exist, nothing will
        happen.

        Args:
            name (str): Header name, case-insensitive.
        """

        # NOTE(nateyo): Could use .pop like before, but I imagine it's slightly
        #               slower and we weren't returning before anyway.
        try:
            del self._headers[name.lower()]
        except KeyError:
            pass

    def normalized(self):
        """
        Normalizes the header dictionary to a list of tuples with type ``str``.
        The functions in ``_normalizers`` are used to convert header value lists
        to ``str``. 

        Returns:
            list: Header tuples (``str``, ``str``) where
                  [0] = Header name
                  [1] = Header value
        """
        # NOTE(nateyo): Needs some perf testing. Also, like most list
        #               list comprehensions, it's unreadable.
        return [(name, self._normalizers[name](self._headers[name]),)
                for name in self._headers]

    def set_headers(self, headers):
        """Set several headers at once.

        Warning:
            Calling this method overwrites existing values, if any.

        Args:
            headers (dict or list): A dictionary of header names and values
                to set, or a ``list`` of (*name*, *value*) tuples. Both *name*
                and *value* must be of type ``str`` or ``StringType`` and
                contain only US-ASCII characters. Under Python 2.x, the
                ``unicode`` type is also accepted, although such strings are
                also limited to US-ASCII.

                Note:
                    Falcon can process a list of tuples slightly faster
                    than a dict.

        Raises:
            ValueError: `headers` was not a ``dict`` or ``list`` of ``tuple``.

        """

        if isinstance(headers, dict):
            headers = headers.items()

        # NOTE(kgriffs): We can't use dict.update because we have to
        # normalize the header names.
        _headers = self._headers

        for name, value in headers:
            # NOTE(kgriffs): uwsgi fails with a TypeError if any header
            # is not a str, so do the conversion here. It's actually
            # faster to not do an isinstance check. str() will encode
            # to US-ASCII.
            name = str(name)
            value = str(value)

            _headers[name.lower()] = value

    cache_control = header_property(
        'Cache-Control',
        """Set the Cache-Control header.

        Expects a list of cache directives to use as the value of the
        Cache-Control header, although a single `str` value is also
        accepted.
        """)

    content_location = header_property(
        'Content-Location',
        """Set the Content-Location header.

        This value will be URI encoded per RFC 3986. If the value that is
        being set is already URI encoded it should be decoded first or the
        header should be set manually using the add method.
        """,
        uri_encode)

    content_length = header_property(
        'Content-Length',
        """Set the Content-Length header.

        Useful for responding to HEAD requests when you aren't actually
        providing the response body.

        Note:
            In cases where the response content is a stream (readable
            file-like object), Falcon will not supply a Content-Length header
            to the WSGI server unless `content_length` is explicitly set.
            Consequently, the server may choose to use chunked encoding or one of the
            other strategies suggested by PEP-3333.

        """,
    )

    content_range = header_property(
        'Content-Range',
        """A tuple to use in constructing a value for the Content-Range header.

        The tuple has the form (*start*, *end*, *length*, [*unit*]), where *start* and
        *end* designate the range (inclusive), and *length* is the
        total length, or '\\*' if unknown. You may pass ``int``'s for
        these numbers (no need to convert to ``str`` beforehand). The optional value
        *unit* describes the range unit and defaults to 'bytes'

        Note:
            You only need to use the alternate form, 'bytes \\*/1234', for
            responses that use the status '416 Range Not Satisfiable'. In this
            case, raising ``falcon.HTTPRangeNotSatisfiable`` will do the right
            thing.

        (See also: RFC 7233, Section 4.2)
        """,
        format_range)

    content_type = header_property(
        'Content-Type',
        """Sets the Content-Type header.

        The ``falcon`` module provides a number of constants for
        common media types, including ``falcon.MEDIA_JSON``,
        ``falcon.MEDIA_MSGPACK``, ``falcon.MEDIA_YAML``,
        ``falcon.MEDIA_XML``, ``falcon.MEDIA_HTML``,
        ``falcon.MEDIA_JS``, ``falcon.MEDIA_TEXT``,
        ``falcon.MEDIA_JPEG``, ``falcon.MEDIA_PNG``,
        and ``falcon.MEDIA_GIF``.
        """)

    downloadable_as = header_property(
        'Content-Disposition',
        """Set the Content-Disposition header using the given filename.

        The value will be used for the *filename* directive. For example,
        given ``'report.pdf'``, the Content-Disposition header would be set
        to: ``'attachment; filename="report.pdf"'``.
        """,
        format_content_disposition)

    etag = header_property(
        'ETag',
        """Set the ETag header.

        The ETag header will be wrapped with double quotes ``"value"`` in case
        the user didn't pass it.
        """,
        format_etag_header)

    expires = header_property(
        'Expires',
        """Set the Expires header. Set to a ``datetime`` (UTC) instance.

        Note:
            Falcon will format the ``datetime`` as an HTTP date string.
        """,
        dt_to_http)

    last_modified = header_property(
        'Last-Modified',
        """Set the Last-Modified header. Set to a ``datetime`` (UTC) instance.

        Note:
            Falcon will format the ``datetime`` as an HTTP date string.
        """,
        dt_to_http)

    location = header_property(
        'Location',
        """Set the Location header.

        This value will be URI encoded per RFC 3986. If the value that is
        being set is already URI encoded it should be decoded first or the
        header should be set manually using the set_header method.
        """,
        uri_encode)

    retry_after = header_property(
        'Retry-After',
        """Set the Retry-After header.

        The expected value is an integral number of seconds to use as the
        value for the header. The HTTP-date syntax is not supported.
        """,
        str)

    vary = header_property(
        'Vary',
        """Value to use for the Vary header.

        Set this property to an iterable of header names, or a single value
        ``str`` which will be automatically converted to a single item ``list``.

        The "Vary" header field in a response describes what parts of
        a request message, aside from the method, Host header field,
        and request target, might influence the origin server's
        process for selecting and representing this response.  The
        value consists of either a single asterisk ("*") or a list of
        header field names (case-insensitive).

        (See also: RFC 7231, Section 7.1.4)
        """)

    accept_ranges = header_property(
        'Accept-Ranges',
        """Set the Accept-Ranges header.

        The Accept-Ranges header field indicates to the client which
        range units are supported (e.g. "bytes") for the target
        resource.

        If range requests are not supported for the target resource,
        the header may be set to "none" to advise the client not to
        attempt any such requests.

        Note:
            "none" is the literal string, not Python's built-in ``None``
            type.

        """)

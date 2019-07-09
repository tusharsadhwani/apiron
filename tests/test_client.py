from unittest import mock

import pytest

from apiron import client, NoHostsAvailableException


class TestClient:
    @mock.patch("requests.sessions.Session", autospec=True)
    def test_get_adapted_session(self, mock_session):
        adapter = mock.Mock()
        adapted_session = client.get_adapted_session(adapter)
        assert adapter == adapted_session.get_adapter("http://foo.com")
        assert adapter == adapted_session.get_adapter("https://foo.com")

    def test_get_required_headers(self):
        service = mock.Mock()
        service.required_headers = {"one": "two"}
        endpoint = mock.Mock()
        endpoint.required_headers = {"foo": "bar"}
        expected_headers = {}
        expected_headers.update(service.required_headers)
        expected_headers.update(endpoint.required_headers)
        assert expected_headers == client.get_required_headers(service, endpoint)

    @mock.patch("apiron.client.requests.Request")
    @mock.patch("apiron.client.get_required_headers")
    def test_build_request_object_passes_arguments_to_request_constructor(
        self, mock_get_required_headers, mock_request_constructor
    ):
        session = mock.Mock()

        service = mock.Mock()
        service.get_hosts.return_value = ["http://host1.biz"]

        endpoint = mock.Mock()
        endpoint.default_method = "POST"
        endpoint.get_formatted_path.return_value = "/foo"
        endpoint.required_headers = {"header": "value"}
        endpoint.default_params = {}
        endpoint.required_params = set()

        params = {"baz": "qux"}
        endpoint.get_merged_params.return_value = params
        data = "I am a data"
        json = {"raw": "data"}
        headers = {"Accept": "stuff"}
        cookies = {"chocolate-chip": "yes"}
        auth = mock.Mock()

        mock_get_required_headers.return_value = {"header": "value"}
        expected_headers = {}
        expected_headers.update(headers)
        expected_headers.update(endpoint.required_headers)

        with mock.patch.object(session, "prepare_request") as mock_prepare_request:
            client.build_request_object(
                session,
                service,
                endpoint,
                params=params,
                data=data,
                json=json,
                headers=headers,
                cookies=cookies,
                auth=auth,
                foo="bar",
            )

            mock_request_constructor.assert_called_once_with(
                url="http://host1.biz/foo",
                method=endpoint.default_method,
                headers=expected_headers,
                cookies=cookies,
                params=params,
                data=data,
                json=json,
                auth=auth,
            )

            assert 1 == mock_prepare_request.call_count

    @mock.patch("apiron.client.Timeout")
    @mock.patch("apiron.client.get_adapted_session")
    @mock.patch("apiron.client.build_request_object")
    @mock.patch("requests.adapters.HTTPAdapter", autospec=True)
    @mock.patch("requests.Session", autospec=True)
    def test_call(self, MockSession, MockAdapter, mock_build_request_object, mock_get_adapted_session, mock_timeout):
        service = mock.Mock()
        service.get_hosts.return_value = ["http://host1.biz"]

        endpoint = mock.Mock()
        endpoint.default_method = "GET"
        endpoint.get_formatted_path.return_value = "/foo/"
        endpoint.required_headers = {}
        endpoint.streaming = True
        del endpoint.stub_response

        request = mock.Mock()
        request.url = "http://host1.biz/foo/"
        mock_build_request_object.return_value = request

        mock_logger = mock.Mock()

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.url = "http://host1.biz/foo/"
        mock_response.history = []

        mock_session = MockSession()
        mock_session.send.return_value = mock_response
        mock_get_adapted_session.return_value = mock_session

        client.call(service, endpoint, timeout_spec=mock_timeout, logger=mock_logger)

        mock_get_adapted_session.assert_called_once_with(MockAdapter())
        mock_session.send.assert_called_once_with(
            request,
            timeout=(mock_timeout.connection_timeout, mock_timeout.read_timeout),
            stream=endpoint.streaming,
            allow_redirects=True,
        )

        mock_logger.info.assert_any_call("GET http://host1.biz/foo/")
        mock_logger.info.assert_any_call("200 http://host1.biz/foo/")

        endpoint.default_method = "POST"
        request.method = "POST"

        client.call(service, endpoint, session=mock_session, timeout_spec=mock_timeout, logger=mock_logger)

        mock_session.send.assert_any_call(
            request,
            timeout=(mock_timeout.connection_timeout, mock_timeout.read_timeout),
            stream=endpoint.streaming,
            allow_redirects=True,
        )

        mock_logger.info.assert_any_call("GET http://host1.biz/foo/")
        mock_logger.info.assert_any_call("200 http://host1.biz/foo/")

        request.method = "PUT"

        client.call(
            service, endpoint, method="PUT", session=mock_session, timeout_spec=mock_timeout, logger=mock_logger
        )

        mock_session.send.assert_any_call(
            request,
            timeout=(mock_timeout.connection_timeout, mock_timeout.read_timeout),
            stream=endpoint.streaming,
            allow_redirects=True,
        )

    @mock.patch("apiron.client.get_adapted_session")
    def test_call_with_existing_session(self, mock_get_adapted_session):
        service = mock.Mock()
        service.get_hosts.return_value = ["http://host1.biz"]
        service.required_headers = {}

        endpoint = mock.Mock()
        endpoint.required_headers = {}
        endpoint.get_formatted_path.return_value = "/foo/"
        del endpoint.stub_response

        mock_logger = mock.Mock()
        mock_response = mock.Mock()
        mock_response.history = []

        session = mock.Mock()
        session.send.return_value = mock_response

        client.call(service, endpoint, session=session, logger=mock_logger)

        assert not mock_get_adapted_session.called
        assert not session.close.called

    def test_call_with_explicit_encoding(self):
        service = mock.Mock()
        service.get_hosts.return_value = ["http://host1.biz"]
        service.required_headers = {}

        endpoint = mock.Mock()
        endpoint.required_headers = {}
        endpoint.get_formatted_path.return_value = "/foo/"
        del endpoint.stub_response

        mock_logger = mock.Mock()
        mock_response = mock.Mock()
        mock_response.history = []

        session = mock.Mock()
        session.send.return_value = mock_response

        client.call(service, endpoint, session=session, logger=mock_logger, encoding="FAKE-CODEC")

        assert "FAKE-CODEC" == mock_response.encoding

    def test_build_request_object_raises_no_host_exception(self):
        service = mock.Mock()
        service.get_hosts.return_value = []

        with pytest.raises(NoHostsAvailableException):
            client.build_request_object(None, service, None)

    def test_choose_host(self):
        hosts = ["foo", "bar", "baz"]
        service = mock.Mock()
        service.get_hosts.return_value = hosts
        assert client.choose_host(service) in hosts

    def test_choose_host_raises_exception(self):
        service = mock.Mock()
        service.get_hosts.return_value = []
        with pytest.raises(NoHostsAvailableException):
            client.choose_host(service)


@pytest.mark.parametrize(
    "host,path,url",
    [
        ("http://biz.com", "/endpoint", "http://biz.com/endpoint"),
        ("http://biz.com/", "endpoint", "http://biz.com/endpoint"),
        ("http://biz.com/", "/endpoint", "http://biz.com/endpoint"),
        ("http://biz.com", "endpoint", "http://biz.com/endpoint"),
        ("http://biz.com/v2", "/endpoint", "http://biz.com/v2/endpoint"),
        ("http://biz.com/v2/", "endpoint", "http://biz.com/v2/endpoint"),
        ("http://biz.com/v2/", "/endpoint", "http://biz.com/v2/endpoint"),
        ("http://biz.com/v2", "endpoint", "http://biz.com/v2/endpoint"),
    ],
)
def test_build_url(host, path, url):
    assert url == client.build_url(host, path)

# Copyright 2014 Tata Consultancy Services Ltd.
# All Rights Reserved
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import logging
import time
import urllib

import requests
import six.moves.urllib.parse as urlparse

from vnfsvcclient import client
from vnfsvcclient.common import _
from vnfsvcclient.common import constants
from vnfsvcclient.common import exceptions
from vnfsvcclient.common import serializer
from vnfsvcclient.common import utils


_logger = logging.getLogger(__name__)


def exception_handler_v20(status_code, error_content):
    """Exception handler for API v2.0 client

        This routine generates the appropriate
        vnfsvc exception according to the contents of the
        response body

        :param status_code: HTTP error status code
        :param error_content: deserialized body of error response
    """
    error_dict = None
    if isinstance(error_content, dict):
        error_dict = error_content.get('VNFSvcError')
    # Find real error type
    bad_vnfsvc_error_flag = False
    if error_dict:
        # If vnfsvc key is found, it will definitely contain
        # a 'message' and 'type' keys?
        try:
            error_type = error_dict['type']
            error_message = error_dict['message']
            if error_dict['detail']:
                error_message += "\n" + error_dict['detail']
        except Exception:
            bad_vnfsvc_error_flag = True
        if not bad_vnfsvc_error_flag:
            # If corresponding exception is defined, use it.
            client_exc = getattr(exceptions, '%sClient' % error_type, None)
            # Otherwise look up per status-code client exception
            if not client_exc:
                client_exc = exceptions.HTTP_EXCEPTION_MAP.get(status_code)
            if client_exc:
                raise client_exc(message=error_message,
                                 status_code=status_code)
            else:
                raise exceptions.VNFSvcClientException(
                    status_code=status_code, message=error_message)
        else:
            raise exceptions.VNFSvcClientException(status_code=status_code,
                                                    message=error_dict)
    else:
        message = None
        if isinstance(error_content, dict):
            message = error_content.get('message')
        if message:
            raise exceptions.VNFSvcClientException(status_code=status_code,
                                                    message=message)

    # If we end up here the exception was not a vnfsvc error
    msg = "%s-%s" % (status_code, error_content)
    raise exceptions.VNFSvcClientException(status_code=status_code,
                                            message=msg)


class APIParamsCall(object):
    """A Decorator to add support for format and tenant overriding
       and filters
    """
    def __init__(self, function):
        self.function = function

    def __get__(self, instance, owner):
        def with_params(*args, **kwargs):
            _format = instance.format
            if 'format' in kwargs:
                instance.format = kwargs['format']
            ret = self.function(instance, *args, **kwargs)
            instance.format = _format
            return ret
        return with_params


class Client(object):
    """Client for the OpenStack vnfsvc v2.0 API.

    :param string username: Username for authentication. (optional)
    :param string user_id: User ID for authentication. (optional)
    :param string password: Password for authentication. (optional)
    :param string token: Token for authentication. (optional)
    :param string tenant_name: Tenant name. (optional)
    :param string tenant_id: Tenant id. (optional)
    :param string auth_url: Keystone service endpoint for authorization.
    :param string endpoint_type: VNF service endpoint type to pull from the
                                 keystone catalog (e.g. 'publicURL',
                                 'internalURL', or 'adminURL') (optional)
    :param string region_name: Name of a region to select when choosing an
                               endpoint from the service catalog.
    :param string endpoint_url: A user-supplied endpoint URL for the vnfsvc
                            service.  Lazy-authentication is possible for API
                            service calls if endpoint is set at
                            instantiation.(optional)
    :param integer timeout: Allows customization of the timeout for client
                            http requests. (optional)
    :param bool insecure: SSL certificate validation. (optional)
    :param string ca_cert: SSL CA bundle file to use. (optional)
    :param integer retries: How many times idempotent (GET, PUT, DELETE)
                            requests to vnfsvc server should be retried if
                            they fail (default: 0).
    :param bool raise_errors: If True then exceptions caused by connection
                              failure are propagated to the caller.
                              (default: True)
    :param session: Keystone client auth session to use. (optional)
    :param auth: Keystone auth plugin to use. (optional)

    Example::

        from vnfsvcclient.v1_0 import client
        vnfsvc = client.Client(username=USER,
                                password=PASS,
                                tenant_name=TENANT_NAME,
                                auth_url=KEYSTONE_URL)

        services = vnfsvc.list_services()
        ...

    """

    services_path = '/services'
    service_path = '/services/%s'
    templates_path = '/templates'
    template_path = '/templates/%s'
    activates_path = '/activates'
    activate_path = '/activates/%s'
    metrics_path = '/metrics'
    metric_path = '/metrics/%s'
    service_drivers_path = '/service_drivers'
    service_driver_path = '/service_drivers/%s'
    diagnostics_path = '/diagnostics'
    diagnostic_path = '/diagnostics/%s'
    configurations_path = '/configurations'
    configuration_path = '/configurations/%s'
    registers_path = '/registers'
    register_path = '/registers/%s'
    dumpxml_path = '/dumpxmls/%s'


    # API has no way to report plurals, so we have to hard code them
    EXTED_PLURALS = {}
    # 8192 Is the default max URI len for eventlet.wsgi.server
    MAX_URI_LEN = 8192

    def get_attr_metadata(self):
        if self.format == 'json':
            return {}
        old_request_format = self.format
        self.format = 'json'
        exts = self.list_extensions()['extensions']
        self.format = old_request_format
        ns = dict([(ext['alias'], ext['namespace']) for ext in exts])
        self.EXTED_PLURALS.update(constants.PLURALS)
        return {'plurals': self.EXTED_PLURALS,
                'xmlns': constants.XML_NS_V20,
                constants.EXT_NS: ns}

    @APIParamsCall
    def list_services(self, retrieve_all=True, **_params):
        return self.list('services', self.services_path, retrieve_all, **_params)

    @APIParamsCall
    def show_service(self, service, **_params):
        return self.get(self.service_path % service, params=_params)

    @APIParamsCall
    def update_service(self, service, body=None):
        return self.put(self.service_path % service, body=body)

    @APIParamsCall
    def create_service(self, body=None):
        return self.post(self.services_path, body=body)
    
    @APIParamsCall
    def delete_service(self, service):
        return self.delete(self.service_path % service)


    @APIParamsCall
    def list_templates(self, retrieve_all=True, **_params):
        return self.list('templates', self.templates_path, retrieve_all, **_params)

    @APIParamsCall
    def create_template(self, body=None):
        return self.post(self.templates_path, body=body)

    # ADDED BY ANIRUDH FOR METRICS
    @APIParamsCall
    def show_metric(self, metric, **_params):
        return self.get(self.metric_path % metric, params=_params)

    @APIParamsCall
    def list_metrics(self, retrieve_all=True, **_params):
        return self.list('metrics', self.metrics_path, retrieve_all, **_params)
    # ENDS HERE

    # ADDED BY ANIRUDH

    @APIParamsCall
    def create_configuration(self, body=None):
        return self.post(self.configurations_path, body=body)

    @APIParamsCall
    def update_configuration(self, configuration, body=None):
        return self.put(self.configuration_path % configuration, body=body)

    @APIParamsCall
    def list_configurations(self, retrieve_all=True, **_params):
        return self.list('configurations', self.configurations_path, retrieve_all, **_params)


    @APIParamsCall
    def show_service_driver(self, service_driver, **_params):
        return self.get(self.service_driver_path % service_driver, params=_params)

    @APIParamsCall
    def list_service_drivers(self, retrieve_all=True, **_params):
        return self.list('service_drivers', self.service_drivers_path, retrieve_all, **_params)
    # ENDS HERE

    @APIParamsCall
    def create_activate(self,body=None):
        return self.post(self.activates_path, body=body)


    @APIParamsCall
    def delete_template(self, template):
        return self.delete(self.template_path % template)
    @APIParamsCall
    def show_template(self, template, **_params):
        return self.get(self.template_path % template, params=_params)

    @APIParamsCall
    def list_diagnostics(self, retrieve_all=True, **_params):
        return self.list('diagnostics', self.diagnostics_path, retrieve_all, **_params)

    @APIParamsCall
    def create_diagnostic(self, body=None):
        return self.post(self.diagnostics_path, body=body)

    @APIParamsCall
    def delete_diagnostic(self, nsd):
        return self.delete(self.diagnostic_path % nsd)

    @APIParamsCall
    def list_dumpxmls(self, retrieve_all=True, **_params):
        data = self.list('services', self.services_path, retrieve_all, **_params)
        data['dumpxmls'] = data['services']
        del data['services']
        return data

    @APIParamsCall
    def show_dumpxml(self, service, **_params):
        dict_data = self.get(self.dumpxml_path % service, params=_params)
        return dict_data

    @APIParamsCall
    def create_register(self, body=None):
        return self.post(self.registers_path, body=body)


    def __init__(self, **kwargs):
        """Initialize a new client for the vnfsvc v2.0 API."""
        super(Client, self).__init__()
        self.retries = kwargs.pop('retries', 0)
        self.raise_errors = kwargs.pop('raise_errors', True)
        self.httpclient = client.construct_http_client(**kwargs)
        self.version = '1.0'
        self.format = 'json'
        self.action_prefix = "/v%s" % (self.version)
        self.retry_interval = 1

    def _handle_fault_response(self, status_code, response_body):
        # Create exception with HTTP status code and message
        _logger.debug("Error message: %s", response_body)
        # Add deserialized error message to exception arguments
        try:
            des_error_body = self.deserialize(response_body, status_code)
        except Exception:
            # If unable to deserialized body it is probably not a
            # vnfsvc error
            des_error_body = {'message': response_body}
        # Raise the appropriate exception
        exception_handler_v20(status_code, des_error_body)

    def _check_uri_length(self, action):
        uri_len = len(self.httpclient.endpoint_url) + len(action)
        if uri_len > self.MAX_URI_LEN:
            raise exceptions.RequestURITooLong(
                excess=uri_len - self.MAX_URI_LEN)

    def do_request(self, method, action, body=None, headers=None, params=None):
        # Add format and tenant_id
        action += ".%s" % self.format
        action = self.action_prefix + action
        if type(params) is dict and params:
            params = utils.safe_encode_dict(params)
            action += '?' + urllib.urlencode(params, doseq=1)
        # Ensure client always has correct uri - do not guesstimate anything
        self.httpclient.authenticate_and_fetch_endpoint_url()
        self._check_uri_length(action)

        if body:
            body = self.serialize(body)
        self.httpclient.content_type = self.content_type()
        resp, replybody = self.httpclient.do_request(action, method, body=body)
        status_code = resp.status_code
        if status_code in (requests.codes.ok,
                           requests.codes.created,
                           requests.codes.accepted,
                           requests.codes.no_content):
            return self.deserialize(replybody, status_code)
        else:
            if not replybody:
                replybody = resp.reason
            self._handle_fault_response(status_code, replybody)

    def get_auth_info(self):
        return self.httpclient.get_auth_info()

    def serialize(self, data):
        """Serializes a dictionary into either XML or JSON.

        A dictionary with a single key can be passed and
        it can contain any structure.
        """
        if data is None:
            return None
        elif type(data) is dict:
            return serializer.Serializer(
                self.get_attr_metadata()).serialize(data, self.content_type())
        else:
            raise Exception(_("Unable to serialize object of type = '%s'") %
                            type(data))

    def deserialize(self, data, status_code):
        """Deserializes an XML or JSON string into a dictionary."""
        if status_code == 204:
            return data
        return serializer.Serializer(self.get_attr_metadata()).deserialize(
            data, self.content_type())['body']

    def content_type(self, _format=None):
        """Returns the mime-type for either 'xml' or 'json'.

        Defaults to the currently set format.
        """
        _format = _format or self.format
        return "application/%s" % (_format)

    def retry_request(self, method, action, body=None,
                      headers=None, params=None):
        """Call do_request with the default retry configuration.

        Only idempotent requests should retry failed connection attempts.
        :raises: ConnectionFailed if the maximum # of retries is exceeded
        """
        max_attempts = self.retries + 1
        for i in range(max_attempts):
            try:
                return self.do_request(method, action, body=body,
                                       headers=headers, params=params)
            except exceptions.ConnectionFailed:
                # Exception has already been logged by do_request()
                if i < self.retries:
                    _logger.debug('Retrying connection to vnfsvc service')
                    time.sleep(self.retry_interval)
                elif self.raise_errors:
                    raise

        if self.retries:
            msg = (_("Failed to connect to vnfsvc server after %d attempts")
                   % max_attempts)
        else:
            msg = _("Failed to connect vnfsvc server")

        raise exceptions.ConnectionFailed(reason=msg)

    def delete(self, action, body=None, headers=None, params=None):
        return self.retry_request("DELETE", action, body=body,
                                  headers=headers, params=params)

    def get(self, action, body=None, headers=None, params=None):
        return self.retry_request("GET", action, body=body,
                                  headers=headers, params=params)

    def post(self, action, body=None, headers=None, params=None):
        # Do not retry POST requests to avoid the orphan objects problem.
        return self.do_request("POST", action, body=body,
                               headers=headers, params=params)

    def put(self, action, body=None, headers=None, params=None):
        return self.retry_request("PUT", action, body=body,
                                  headers=headers, params=params)

    def list(self, collection, path, retrieve_all=True, **params):
        if retrieve_all:
            res = []
            for r in self._pagination(collection, path, **params):
                res.extend(r[collection])
            return {collection: res}
        else:
            return self._pagination(collection, path, **params)

    def _pagination(self, collection, path, **params):
        if params.get('page_reverse', False):
            linkrel = 'previous'
        else:
            linkrel = 'next'
        next = True
        while next:
            res = self.get(path, params=params)
            yield res
            next = False
            try:
                for link in res['%s_links' % collection]:
                    if link['rel'] == linkrel:
                        query_str = urlparse.urlparse(link['href']).query
                        params = urlparse.parse_qs(query_str)
                        next = True
                        break
            except KeyError:
                break

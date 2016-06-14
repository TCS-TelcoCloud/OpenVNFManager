# Copyright 2014 Tata Consultancy Services Ltd.
# All Rights Reserved.
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

"""
Vnfsvc base exception handling.
"""

from vnfsvc.openstack.common import excutils
from vnfsvc.openstack.common.gettextutils import _

class VNFSvcException(Exception):
    """Base Vnfsvc Exception.

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.
    """
    message = _("An unknown exception occurred.")

    def __init__(self, **kwargs):
        try:
            super(VNFSvcException, self).__init__(self.message % kwargs)
            self.msg = self.message % kwargs
        except Exception:
            with excutils.save_and_reraise_exception() as ctxt:
                if not self.use_fatal_exceptions():
                    ctxt.reraise = False
                    # at least get the core message out if something happened
                    super(VNFSvcException, self).__init__(self.message)

    def __unicode__(self):
        return unicode(self.msg)

    def use_fatal_exceptions(self):
        return False


class BadRequest(VNFSvcException):
    message = _('Bad %(resource)s request: %(msg)s')


class NotFound(VNFSvcException):
    pass


class Conflict(VNFSvcException):
    pass


class NotAuthorized(VNFSvcException):
    message = _("Not authorized.")


class ServiceUnavailable(VNFSvcException):
    message = _("The service is unavailable")


class AdminRequired(NotAuthorized):
    message = _("User does not have admin privileges: %(reason)s")



class StateInvalid(BadRequest):
    message = _("Unsupported port state: %(port_state)s")


class InUse(VNFSvcException):
    message = _("The resource is inuse")



class ResourceExhausted(ServiceUnavailable):
    pass


class MalformedRequestBody(BadRequest):
    message = _("Malformed request body: %(reason)s")


class Invalid(VNFSvcException):
    def __init__(self, message=None):
        self.message = message
        super(Invalid, self).__init__()


class InvalidInput(BadRequest):
    message = _("Invalid input for operation: %(error_message)s.")


class SudoRequired(VNFSvcException):
    message = _("Sudo privilege is required to run this command.")


class InvalidContentType(VNFSvcException):
    message = _("Invalid content type %(content_type)s")



class InvalidConfigurationOption(VNFSvcException):
    message = _("An invalid value was provided for %(opt_name)s: "
                "%(opt_value)s")

class NoRouterException(VNFSvcException):
    message = _("No Router found")

class NoSuchVDUException(VNFSvcException):
    message = _("Unable to find vdu ID")

class NoSuchNSDException(VNFSvcException):
    message = _("Unable to find nsd ID")

class InstanceException(VNFSvcException):
    messgae = _("Unable to launch instance")

class DriverException(VNFSvcException):
    message = _("Driver Exception occured.")

class ConfigurationException(VNFSvcException):
    message = _("Unable to configure VNF")

class NoVduforNsd(VNFSvcException):
    message = _("No such Vdus found for the NSD.")

class ServiceException(VNFSvcException):
    message = _("Service name already exists")


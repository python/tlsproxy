from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker, MultiService
from twisted.application import internet
from twisted.internet import reactor
from twisted.internet.endpoints import serverFromString

from tlsproxy import ProxyFactory


class Options(usage.Options, object):

    optParameters = [
        ["proxy-to", "p", None, "The server to proxy to."],
    ]

    def __init__(self, *args, **kwargs):
        super(Options, self).__init__(*args, **kwargs)

        self["bind"] = []

    def opt_bind(self, bind):
        self["bind"].append(bind)

    opt_b = opt_bind


class TLSProxyServiceMaker(object):
    implements(IServiceMaker, IPlugin)

    tapname = "tlsproxy"
    description = (
        "A front end for HAProxy or other PROXY protocol speaking servers "
        "that unwraps TLS."
    )
    options = Options

    def makeService(self, options):
        factory = ProxyFactory(options["proxy-to"])
        serviceContainer = MultiService()

        for bind in options["bind"]:
            endpoint = serverFromString(reactor, bind)
            service = internet.StreamServerEndpointService(endpoint, factory)
            service.setServiceParent(serviceContainer)

        return serviceContainer


serviceMaker = TLSProxyServiceMaker()

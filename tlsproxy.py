import collections
import struct

import bitstring
import ipaddress
import six

from twisted.internet import address, reactor as globalReactor
from twisted.internet.endpoints import clientFromString
from twisted.protocols.portforward import (
    ProxyFactory as _ProxyFactory,
    ProxyServer as _ProxyServer,
    ProxyClientFactory as _ProxyClientFactory,
    ProxyClient as _ProxyClient,
)


_PROXY_HEADER = b"\x0D\x0A\x0D\x0A\x00\x0D\x0A\x51\x55\x49\x54\x0A"
_PROXY_VERSION = 2
_PROXY_COMMANDS = {
    "LOCAL": 0,
    "PROXY": 1,
}
_PROXY_AF = collections.defaultdict(
    lambda: 0,
    {
        address.IPv4Address: 1,
        address.IPv6Address: 2,
        address.UNIXAddress: 3,
    },
)
_PROXY_PROTOCOL = collections.defaultdict(lambda: 0, {"TCP": 1, "UDP": 2})


_LengthStruct = struct.Struct("!H")
_IPv4Stuct = struct.Struct("!4s4sHH")
_IPv6Struct = struct.Struct("!16s16sHH")
_UnixStruct = struct.Struct("!108s108s")


class ProxyClient(_ProxyClient, object):

    def connectionMade(self):
        # Yank out our peer/host addresses as we'll need them to construct our
        # header.
        peer = self.peer.transport.getPeer()
        peer_parsed = ipaddress.ip_address(six.text_type(peer.host))
        host = self.peer.transport.getHost()
        host_parsed = ipaddress.ip_address(six.text_type(host.host))

        # All of our PROXY data needs to start with this header to indicate
        # that it is the PROXY v2 protocol.
        data = [_PROXY_HEADER]

        # We need to communicate what version of the protocol we speak (v2) and
        # what kind of command this is. Currently we only support the Proxy
        # commands.
        data.append(
            bitstring.pack(
                "int:4, int:4",
                _PROXY_VERSION,
                _PROXY_COMMANDS["PROXY"],
            ).bytes
        )

        # We also need to communicate what type of connection this is, like an
        # IPv4 over TCP or so.
        data.append(
            bitstring.pack(
                "int:4, int:4",
                _PROXY_AF[peer.__class__],
                _PROXY_PROTOCOL[peer.type],
            ).bytes
        )

        # Here we need to add what the length of the rest of our data is,
        # however we don't actually *have* the rest of out data yet, so we'll
        # just add a junk value here for now and come back to this later.
        data.append(None)

        # We need to send information about our client and what they connected
        # to, and the exact format of that will change based on the address
        # family of the connection.
        if isinstance(peer, address.IPv4Address):
            data.append(_IPv4Stuct.pack(
                peer_parsed.packed,
                host_parsed.packed,
                peer.port,
                host.port,
            ))
        elif isinstance(peer, address.IPv6Address):
            data.append(_IPv6Struct.pack(
                peer_parsed.packed,
                host_parsed.packed,
                peer.port,
                host.port,
            ))
        elif isinstance(peer, address.UNIXAddress):
            data.append(_UnixStruct.pack(
                peer.name,
                host.name,
            ))

        # TODO: Insert TLS Stuff
        # We can only actually do this for one of our known address types,
        # otherwise we have to have a length of zero for the rest of the data.
        if isinstance(peer, tuple(_PROXY_AF.keys())):
            pass

        # Now that we've finished building up our message, we'll figure out
        # what the length of our header block is.
        data[3] = _LengthStruct.pack(sum(map(len, data[4:])))

        # Send this all to the server we're proxying for so that it can set its
        # own internal state correctly.
        self.transport.writeSequence(data)

        # Finally, we'll call the standard connectionMade, which will finish
        # constructing our tunnel.
        return super(ProxyClient, self).connectionMade()


class ProxyClientFactory(_ProxyClientFactory, object):
    protocol = ProxyClient


class ProxyServer(_ProxyServer, object):

    clientProtocolFactory = ProxyClientFactory

    def connectionMade(self):
        # Don't read anything from the connecting client until we have
        # somewhere to send it to.
        self.transport.pauseProducing()

        client = self.clientProtocolFactory()
        client.setServer(self)

        self.factory.endpoint.connect(client)


class ProxyFactory(_ProxyFactory, object):
    protocol = ProxyServer

    def __init__(self, endpoint, reactor=None):
        if reactor is None:
            reactor = globalReactor
        self.endpoint = clientFromString(reactor, endpoint)

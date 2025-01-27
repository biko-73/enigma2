openatv_like = True
try:
  # This works in OpenATV (and similar code bases) but fails on OpenPLi.
  # The particular import might not be relevant for the actual plugin.
  from Screens.EpgSelection import SingleEPG
  ADJUST={'adjust': False}
except:
  ADJUST={}
  openatv_like = False

# Quick fix for Vix
try:
  import boxbranding
  if "openvix" in boxbranding.getImageDistro().lower():
    openatv_like = True
except:
  pass

# For plugins without using SingleEPG only!
try:
  import boxbranding
  if 'openspa' in boxbranding.getImageDistro().lower():
    openatv_like = True
except:
  pass

import re
#import upnpclient
import urlparse
import socket
import struct
import threading
import time
import traceback

from enigma import eTimer

DEBUG_ACTIVE_DEF=False
DEBUG_ACTIVE=DEBUG_ACTIVE_DEF
DEBUG_FILE='/tmp/pfchangs-debug.log'


def DEBUG(s):
  if DEBUG_ACTIVE:
    t = time.ctime()
    f = open(DEBUG_FILE, 'a+')
    f.write('%s %s' % (t, s))
    f.close()
    print '%s %s' % (t,s)


def getGateway():
  DEBUG('getGateway()\n')
  try:
    with open('/proc/net/route') as fh:
      for line in fh:
        DEBUG('%s\n' % line)
        fields = line.strip().split()
        if fields[1] != '00000000' or not int(fields[3], 16) & 2:
          continue
        return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
  except:
    DEBUG('%s\n' % traceback.format_exc())
  return ''


def getIntIP(gateway=None):
  DEBUG('getIntIP()\n')
  if gateway:
   try:
     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
     s.connect((gateway, 53))
     int_ip = s.getsockname()[0]
     s.close()
     DEBUG('%s\n' % int_ip)
     return int_ip
   except:
     DEBUG('%s\n' % traceback.format_exc())
   return ''


def getMethods(gateway=None):
  DEBUG('getMethods()\n')
  try:
#    ssdp = upnpclient.SSDP()
    ssdp = SSDP()
    servers = ssdp.discover()
    if gateway:
      for server in servers:
        DEBUG('%s: %s\n' % (server.friendly_name, server.model_description))
        hostname = urlparse.urlparse(server.location).hostname
        if gateway == hostname:
          DEBUG('Found GW: %s (%s)\n' % (server.location, server.friendly_name))
          get_gen_port_map = server.find_action('GetGenericPortMappingEntry')
          add_port_map = server.find_action('AddPortMapping')
          del_port_map = server.find_action('DeletePortMapping')
          get_ext_ip = server.find_action('GetExternalIPAddress')
          DEBUG('%s, %s, %s, %s\n' % (get_gen_port_map, add_port_map, del_port_map, get_ext_ip))
          if not (get_gen_port_map and add_port_map and del_port_map and get_ext_ip):
            DEBUG('One or more required UPNP actions missing...\n')
            return None, None, None, None
          return get_gen_port_map, add_port_map, del_port_map, get_ext_ip
  except:
    DEBUG('%s\n' % traceback.format_exc())
  return None, None, None, None


def getExtIP(get_ext_ip=None):
  DEBUG('getExtIP()\n')
  if get_ext_ip:
    try:
      ext_ip = get_ext_ip.call()
      DEBUG('EXT_IP: %s\n' % ext_ip)
      return str(ext_ip.get('NewExternalIPAddress', ''))
    except:
      DEBUG('%s\n' % traceback.format_exc())
  return ''


def getMap(get_gen_port_map=None):
  DEBUG('getMap()\n')
  port_map = []
  if get_gen_port_map:
    try:
      index = 0
      map_entry = get_gen_port_map.call(NewPortMappingIndex=index)
      while map_entry:
        DEBUG('PM(%s): %s\n' % (str(index), map_entry))
        port_map.append(map_entry)
        try:
          index += 1
          map_entry = get_gen_port_map.call(NewPortMappingIndex=index)
        except:
          map_entry = None
    except:
      DEBUG('%s\n' % traceback.format_exc())
    return port_map


def addPortMap(add_port_map=None, int_ip='', ext_port=0, proto='', int_port=0, desc=''):
  DEBUG('addPortMap()\n')
  if add_port_map and int_ip and ext_port and proto and int_port:
    try:
      add_port_map.call(NewRemoteHost='', NewExternalPort=ext_port, NewProtocol=proto,
                        NewInternalPort=int_port, NewInternalClient=int_ip, NewEnabled='true',
                        NewPortMappingDescription=desc, NewLeaseDuration=0)
    except:
      DEBUG('%s\n' % traceback.format_exc())


def delPortMap(del_port_map=None, ext_port=0, proto=''):
  DEBUG('delPortMap()\n')
  if del_port_map:
    try:
      del_port_map.call(NewRemoteHost='', NewExternalPort=ext_port, NewProtocol=proto)
    except:
      DEBUG('%s\n' % traceback.format_exc())


from Components.config import config, ConfigBoolean, ConfigNumber, ConfigSelection, ConfigSubsection, ConfigText
from Plugins.Plugin import PluginDescriptor
if openatv_like:
  from Screens.Setup import Setup
else:
  import Screens.Setup
  import xml.etree.cElementTree
  from Components.config import configfile


PLUGIN_VERSION='6.2.0h'
PLUGIN_NAME='PFChangs'
PLUGIN_DESC='UPnP Port Forwarding'
PLUGIN_ICON='pfchangs.png'
PLUGIN_PATH='Extensions/PFChangs'
if not openatv_like:
  PLUGIN_PATH='/usr/lib/enigma2/python/Plugins/' + PLUGIN_PATH
SETUP_KEY='pfchangs'

VERSION_DEF=PLUGIN_VERSION
VERSION_CHOICES=[(VERSION_DEF, VERSION_DEF)]
ENABLE_DEF=False
ENABLE=ENABLE_DEF
##### EXT, INT, GW are read from UPnP/machine
GW = getGateway()
INT = getIntIP(gateway=GW)
GET_MAP, ADD_MAP, DEL_MAP, GET_EXT=getMethods(gateway=GW)
EXT = getExtIP(GET_EXT)
EXT_CHOICES=[(EXT, EXT)]
INT_CHOICES=[(INT, INT)]
GW_CHOICES=[(GW, GW)]
#####
PORTS_STRING_DEF=':tcp:8001,:tcp:8002'
PORTS_STRING=PORTS_STRING_DEF
REFRESH_DEF=15
REFRESH=REFRESH_DEF

MIN_PORT=1
MAX_PORT=65535
PORT_RE='^(?P<ext_port>[0-9]*):(?P<proto>TCP|UDP):(?P<int_port>[0-9]+)$'

MIN_REFRESH=0
MAX_REFRESH=1440

THREAD_LOCK=threading.Lock()
THREAD=None

VISIBLE_WIDTH=20

config.plugins.pfchangs = ConfigSubsection()
config.plugins.pfchangs.enable = ConfigBoolean(default=ENABLE_DEF)
config.plugins.pfchangs.ext = ConfigSelection(default=EXT, choices=EXT_CHOICES)
config.plugins.pfchangs.int = ConfigSelection(default=INT, choices=INT_CHOICES)
config.plugins.pfchangs.gw = ConfigSelection(default=GW, choices=GW_CHOICES)
config.plugins.pfchangs.ports = ConfigText(default=PORTS_STRING_DEF, fixed_size=False, visible_width=VISIBLE_WIDTH)
config.plugins.pfchangs.refresh = ConfigNumber(default=REFRESH_DEF)
config.plugins.pfchangs.debug = ConfigBoolean(default=DEBUG_ACTIVE_DEF)
config.plugins.pfchangs.version = ConfigSelection(default=VERSION_DEF, choices=VERSION_CHOICES)
if not openatv_like:
  SAVED_SETUP=Screens.Setup.setupdom

def addAllMaps(add_port_map=None, int_ip='', ports=''):
  if add_port_map and int_ip and ports:
    try:
      ports = ports.split(',')
      for port in ports:
        m = re.match(PORT_RE, port.upper())
        if m:
          int_port = int(m.group('int_port'))
          proto = m.group('proto')
          ext_port = m.group('ext_port')
          if ext_port:
            ext_port = int(ext_port)
          else:
            ext_port = int_port
          if int_port < MIN_PORT or ext_port < MIN_PORT or int_port > MAX_PORT or ext_port > MAX_PORT:
            continue
          addPortMap(add_port_map=add_port_map, int_ip=int_ip,
                     ext_port=ext_port, proto=proto,
                     int_port=int_port, desc=PLUGIN_NAME)
    except:
      DEBUG('%s\n' % traceback.format_exc())


def delAllMaps(get_gen_port_map=None, del_port_map=None):
  DEBUG('delAllMaps()\n')
  if get_gen_port_map and del_port_map:
    try:
      port_map = getMap(get_gen_port_map=get_gen_port_map)
      for map_entry in port_map:
        desc = str(map_entry.get('NewPortMappingDescription', ''))
        port = map_entry.get('NewExternalPort', 0)
        proto = str(map_entry.get('NewProtocol', ''))
        if PLUGIN_NAME == desc and port and proto:
          delPortMap(del_port_map=del_port_map, ext_port=port, proto=proto)
    except:
      DEBUG('%s\n' % traceback.format_exc())


def refreshAllMaps():
  addAllMaps(add_port_map=ADD_MAP, int_ip=INT, ports=PORTS_STRING)


class refreshThread(threading.Thread):
  def __init__(self, refresh=None):
    DEBUG('refreshThread init!\n')
    threading.Thread.__init__(self)
    self.refresh = refresh
    self.timer = eTimer()
    self.timer.callback.append(self.work)
    self.event = threading.Event()

  def run(self):
    DEBUG('refreshThread run!\n')
    self.timer.start(self.refresh*60*1000, False)
    self.event.wait()

  def work(self):
    DEBUG('refreshThread work!\n')
    THREAD_LOCK.acquire()
    refreshAllMaps()
    THREAD_LOCK.release()

  def stop(self):
    DEBUG('refreshThread stop!\n')
    self.timer.stop()


def reConfig():
  global ENABLE
  global GW
  global INT
  global EXT
  global GET_MAP
  global ADD_MAP
  global DEL_MAP
  global GET_EXT
  global PORTS_STRING
  global REFRESH
  global DEBUG_ACTIVE
  global THREAD
  global THREAD_LOCK

  THREAD_LOCK.acquire()
  if THREAD:
    THREAD.stop()

  GW = getGateway()
  INT = getIntIP(gateway=GW)
  GET_MAP, ADD_MAP, DEL_MAP, GET_EXT=getMethods(gateway=GW)
  EXT = getExtIP(GET_EXT)
  EXT_CHOICES=[(EXT, EXT)]
  INT_CHOICES=[(INT, INT)]
  GW_CHOICES=[(GW, GW)]
  try:
    config.plugins.pfchangs.ext = ConfigSelection(default=EXT, choices=EXT_CHOICES)
    config.plugins.pfchangs.int = ConfigSelection(default=INT, choices=INT_CHOICES)
    config.plugins.pfchangs.gw = ConfigSelection(default=GW, choices=GW_CHOICES)
  except:
    DEBUG('%s\n' % traceback.format_exc())

  PORTS_STRING = config.plugins.pfchangs.ports.value
  if not PORTS_STRING:
    PORTS_STRING = PORTS_STRING_DEF
    config.plugins.pfchangs.ports._value = PORTS_STRING_DEF

  REFRESH = config.plugins.pfchangs.refresh.value
  if REFRESH < MIN_REFRESH or REFRESH > MAX_REFRESH:
    REFRESH = REFRESH_DEF
    config.plugins.pfchangs.refresh._value = REFRESH_DEF

  delAllMaps(get_gen_port_map=GET_MAP, del_port_map=DEL_MAP)
  ENABLE = config.plugins.pfchangs.enable.value
  if ENABLE:
    refreshAllMaps()

  DEBUG_ACTIVE = config.plugins.pfchangs.debug.value
  config.plugins.pfchangs.save()
  if not openatv_like:
    configfile.save()

  if REFRESH and ENABLE:
    THREAD = refreshThread(refresh=REFRESH)
    THREAD.daemon = True
    THREAD.start()
  else:
    THREAD = None

  THREAD_LOCK.release()


def onSetupClose(test=None):
  reConfig()
  if not openatv_like:
    Screens.Setup.setupdom = SAVED_SETUP


def autoStart(reason, **kwargs):
  DEBUG('pfchangs autostart!\n')
  onSetupClose()


def main(session, **kwargs):
  global SAVED_SETUP
  reConfig()
  if session:
    if openatv_like:
      session.openWithCallback(onSetupClose, Setup, setup=SETUP_KEY, plugin=PLUGIN_PATH)
    else:
      try:
        setup_file = file(PLUGIN_PATH + '/setup.xml', 'r')
        new_setupdom = xml.etree.cElementTree.parse(setup_file)
        setup_file.close()
        SAVED_SETUP = Screens.Setup.setupdom
        Screens.Setup.setupdom = new_setupdom
        session.openWithCallback(onSetupClose, Screens.Setup.Setup, SETUP_KEY)
        Screens.Setup.setupdom = SAVED_SETUP
      except:
        pass


def Plugins(**kwargs):
  return [
      PluginDescriptor(
          where=PluginDescriptor.WHERE_AUTOSTART,
          fnc=autoStart),
      PluginDescriptor(
          name=PLUGIN_NAME,
          description=PLUGIN_DESC,
          where=PluginDescriptor.WHERE_PLUGINMENU,
          icon=PLUGIN_ICON,
          fnc=main)]


# Copyright (c) 2012-2016, Ferry Boender <ferry.boender@gmail.com>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# Todo:
#  - Allow persistance of discovered servers.
#  - The control point should wait at least the amount of time specified in the
#    MX header for responses to arrive from devices.
#  - Date/datetime
#  - Store all properties
#  - SSDP.discover(st): Allow to discover only certain service types
#  - .find() method on most classes.
#  - async discover (if possible).
#  - Read parameter types and verify them when doing a call.
#  - Marshall return values to the correct databases.
#  - Handle SOAP error: 
#    <?xml version="1.0"?>
#    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
#     <s:Body>
#      <s:Fault>
#       <faultcode>s:Client</faultcode>
#       <faultstring>UPnPError</faultstring>
#       <detail>
#        <UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
#          <errorCode xmlns="">714</errorCode>
#          <errorDescription xmlns="">No such entry in array</errorDescription>
#        </UPnPError>
#       </detail>
#      </s:Fault>
#     </s:Body>
#    </s:Envelope>
#  - Test params and responses with XML entities in them "<", "&", etc.
#  - AllowedValueRange
#    <allowedValueRange>
#      <minimum>minimum value</minimum>
#      <maximum>maximum value</maximum>
#      <step>increment value</step>
#    </allowedValueRange>
#  - Name params as 'NewFoo', or not (See spec)?

"""
This module provides an UPnP Control Point (client), and provides an easy
interface to discover and communicate with UPnP servers. It implements SSDP
(Simple Service Discovery Protocol), SCPD (Simple Control Point Definition) and
a minimal SOAP (Simple Object Access Protocol) implementation.

The usual flow for working with UPnP servers is:

- Discover UPnP servers using SSDP.

  SSDP is a simple HTTP-over-UDP protocol. An M-SEARCH HTTP request is broad-
  casted over the network and any UPnP servers should respond with an HTTP
  response. This response includes an URL to an XML file containing information
  about the server. The SSDP.discover() method returns a list of Server
  instances. If you already know the URL of the XML file, you can skip this
  step and instantiate a Server instance directly.

- Inspect Server capabilities using SCPD.

  The XML file returned by UPnP servers during discovery is read and information
  about the server and the services it offers is stored in a Server instance. The
  Server.services property contains a list of Service instances supported by that
  server.

- Inspect Services capabilities using SCPD.

  Each Server may contain more than one Services. For each Service, a separate
  XML file exists. The Service class reads that XML file and determines which
  actions a service supports. The Service.actions property contains a list of
  Action instances supported by that service.

- Inspect an Action using SCPD.

  An Action instance may be inspected to determine which arguments need to be
  passed into it and what it returns. Information on the type and possible
  values of each argument can also be queried.

- Call an Action using SOAP.

  An Action instance may then be called using the Action.call(arguments) method.
  The Action class will verify the correctness of arguments, possibly
  converting them. A SOAP call is then made to the UPnP server and the results
  are returned.

Classes:

* SSDP: Discover UPnP servers using the SSDP class.
* Server: Connect to an UPnP server and retrieve information/capabilities using the Server class.
* Service: Query a Server class instance for the various services it supports.
* Action: Query a Service class instance for the various actions it supports and call them.

Various convenience methods are provided at almost all levels. For instance,
the find_action() methods can directly find a method (by name) in an UPnP
server/service. The call() method can be used at most levels to directly call
an action.

The following example discovers all UPnP servers on the local network and then
dumps all their services and actions:

------------------------------------------------------------------------------
import upnpclient

ssdp = upnpclient.SSDP()
servers = ssdp.discover()

for server in servers:
    print "%s: %s" % (server.friendly_name, server.model_description)
    for service in server.services:
        print "   %s" % (service.service_type)
        for action in service.actions:
            print "      %s" % (action.name)
            for arg_name, arg_def in action.argsdef_in:
                valid = ', '.join(arg_def['allowed_values']) or '*'
                print "          in: %s (%s): %s" % (arg_name, arg_def['datatype'], valid)
            for arg_name, arg_def in action.argsdef_out:
                valid = ', '.join(arg_def['allowed_values']) or '*'
                print "         out: %s (%s): %s" % (arg_name, arg_def['datatype'], valid)
------------------------------------------------------------------------------
"""

import logging
import socket
import struct
import urllib2
import xml.dom.minidom
import sys
from urlparse import urljoin

def _XMLGetNodeText(node):
    """
    Return text contents of an XML node.
    """
    text = []
    for childNode in node.childNodes:
        if childNode.nodeType == node.TEXT_NODE:
            text.append(childNode.data)
    return(''.join(text))

def _XMLFindNodeText(node, tag_name):
    """
    Find the first XML node matching `tag_name` and return its text contents.
    If no node is found, return empty string. Use for non-required nodes.
    """
    target_nodes = node.getElementsByTagName(tag_name)
    try:
        return(_XMLGetNodeText(target_nodes[0]))
    except IndexError:
        return('')

def _getLogger(name):
    """
    Retrieve a logger instance. Checks if a handler is defined so we avoid the
    'No handlers could be found' message.
    """
    logger = logging.getLogger(name)
    if not logging.root.handlers:
        logger.disabled = 1
    return(logger)

class UPNPError(Exception):
    """
    Exceptio class for UPnP errors.
    """
    pass

class SSDP(object):
    """
    Simple Service Discovery Protocol. The SSDP class allows for discovery of
    UPnP devices by broadcasting on the local network. It does so by sending an
    HTTP M-SEARCH command over multicast UDP. The `discover()` method does the
    actual discovering. It returns a list of `upnp.Server` class instances of
    servers that responded. After discovery, these servers can also be accessed
    through the `servers` propery.

    Example:

    >>> ssdp = SSDP(1)
    >>> servers = ssdp.discover()
    >>> print upnpservers
    [<Server 'SpeedTouch 546 5.4.0.14 UPnP/1.0 (0612BH95K)'>, <Server 'Linux/2.6.35-31-generic, UPnP/1.0, Free UPnP Entertainment Service/0.655'>]
    """
    def __init__(self, wait_time=2, listen_port=12333):
        """
        Create a new SSDP class. `wait_time` determines how long to wait for
        responses from servers. `listen_port` determines the UDP port on which
        to send/receive replies.
        """
        self.listen_port = listen_port
        self.wait_time = wait_time
        self._log = _getLogger('SSDP')

    def discover_raw(self):
        """
        Discover UPnP devices on the network via UDP multicast. Returns a list
        of dictionaries, each of which contains the HTTPMU reply headers.
        """
        msg = \
            'M-SEARCH * HTTP/1.1\r\n' \
            'HOST:239.255.255.250:1900\r\n' \
            'MAN:"ssdp:discover"\r\n' \
            'MX:2\r\n' \
            'ST:upnp:rootdevice\r\n' \
            '\r\n'

        # Send discovery broadcast message
        self._log.debug('M-SEARCH broadcast discovery')
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(self.wait_time)
        s.sendto(msg, ('239.255.255.250', 1900) )

        # Wait for replies
        ssdp_replies = []
        servers = []
        try:
            while True:
                self._log.debug('Waiting for replies...')
                data, addr = s.recvfrom(65507)
                ssdp_reply_headers = {}
                for line in data.splitlines():
                    if ':' in line:
                        key, value = line.split(':', 1)
                        ssdp_reply_headers[key.strip().lower()] = value.strip()
                self._log.info('Response from %s:%i %s' % (addr[0], addr[1], ssdp_reply_headers['server']))
                self._log.info('%s:%i at %s' % (addr[0], addr[1], ssdp_reply_headers['location']))
                if not ssdp_reply_headers in ssdp_replies:
                    # Prevent multiple responses from showing up multiple
                    # times.
                    ssdp_replies.append(ssdp_reply_headers)
        except socket.timeout:
            pass

        s.close()
        return(ssdp_replies)

    def discover(self):
        """
        Convenience method to discover UPnP devices on the network. Returns a
        list of `upnp.Server` instances. Any invalid servers are silently
        ignored. If you do not want this, use the `SSDP.discover_raw` method.
        """
        servers = []
        for ssdp_reply in self.discover_raw():
            try:
                upnp_server = Server(ssdp_reply['location'], ssdp_reply['server'])
                servers.append(upnp_server)
            except Exception, e:
                self._log.error('Error \'%s\' for %s' % (e, ssdp_reply['server']))
                pass
        return(servers)

class Server(object):
    """
    UPNP Server represention.
    This class represents an UPnP server. `location` is an URL to a control XML
    file, per UPnP standard section 2.1 ('Device Description'). This MUST match
    the URL as given in the 'Location' header when using discovery (SSDP).
    `server_name` is a name for the server, which may be obtained using the
    SSDP class or may be made up by the caller.

    Raises urllib2.HTTPError when the location is invalid

    Example:

    >>> server = Server('http://192.168.1.254:80/upnp/IGD.xml')
    >>> for service in server.services:
    ...     print service.service_id
    ...
    urn:upnp-org:serviceId:layer3f
    urn:upnp-org:serviceId:wancic
    urn:upnp-org:serviceId:wandsllc:pvc_Internet
    urn:upnp-org:serviceId:wanipc:Internet
    """
    def __init__(self, location, server_name=None):
        """
        Create a new Server instance. `location` is an URL to an XML file
        describing the server's services.
        """
        self.location = location
        if server_name:
            self.server_name = server_name
        else:
            self.server_name = location
        self.services = []
        self._log = _getLogger('SERVER')

        DEBUG('SERVER INIT: (%s)\n' % self.location)
        response = urllib2.urlopen(self.location)
        DEBUG('SERVER RESPONSE: (%s)\n' % response)
        raw_xml = response.read()
        DEBUG('SERVER XML: (%s)\n' % raw_xml)
        self._root_xml = xml.dom.minidom.parseString(raw_xml)
        self.device_type = _XMLFindNodeText(self._root_xml, 'deviceType')
        self.friendly_name = _XMLFindNodeText(self._root_xml, 'friendlyName')
        self.manufacturer = _XMLFindNodeText(self._root_xml, 'manufacturer')
        self.model_description = _XMLFindNodeText(self._root_xml, 'modelDescription')
        self.model_name = _XMLFindNodeText(self._root_xml, 'modelName')
        self.model_number = _XMLFindNodeText(self._root_xml, 'modelNumber')
        self.serial_number = _XMLFindNodeText(self._root_xml, 'serialNumber')
        response.close()

        self._url_base = _XMLFindNodeText(self._root_xml, 'URLBase')
        if self._url_base == '':
            # If no URL Base is given, the UPnP specification says: "the base
            # URL is the URL from which the device description was retrieved"
            self._url_base = self.location
        self._readServices()

    def _readServices(self):
        """
        Read the control XML file and populate self.services with a list of
        services in the form of Service class instances.
        """
        # Build a flat list of all services offered by the UPNP server
        for node in self._root_xml.getElementsByTagName('service'):
            service_type = _XMLGetNodeText(node.getElementsByTagName('serviceType')[0])
            service_id = _XMLGetNodeText(node.getElementsByTagName('serviceId')[0])
            control_url = _XMLGetNodeText(node.getElementsByTagName('controlURL')[0])
            scpd_url = _XMLGetNodeText(node.getElementsByTagName('SCPDURL')[0])
            event_sub_url = _XMLGetNodeText(node.getElementsByTagName('eventSubURL')[0])
            self._log.info('%s: Service "%s" at %s' % (self.server_name, service_type, scpd_url))
            self.services.append(Service(self._url_base, service_type, service_id, control_url, scpd_url, event_sub_url))

    def find_action(self, action_name):
        """Find an action by name.
        Convenience method that searches through all the services offered by
        the Server for an action and returns an Action instance. If the action
        is not found, returns None. If multiple actions with the same name are
        found it returns the first one.
        """
        for service in self.services:
            action = service.find_action(action_name)
            if action:
                return(action)
        return(None)

    def call(self, action_name, args={}, **kwargs):
        """Directly call an action
        Convenience method for quickly finding and calling an Action on a
        Server.
        """
        args = args.copy()
        if kwargs:
            # Allow both a dictionary of arguments and normal named arguments
            args.update(kwargs)

        action = self.find_action(action_name)
        if action:
            return(action.call(args))
        return(None)

    def __repr__(self):
        return("<Server '%s'>" % (self.friendly_name))

class Service(object):
    """
    Service Control Point Definition. This class reads an SCPD XML file and
    parses the actions and state variables. It can then be used to call
    actions.
    """
    # FIXME: marshall call arguments
    # FIXME: Check allowed string values
    def __init__(self, url_base, service_type, service_id, control_url, scpd_url, event_sub_url):
        self._url_base = url_base
        self.service_type = service_type
        self.service_id = service_id
        self._control_url = control_url
        self._scpd_url = scpd_url
        self._event_sub_url = event_sub_url

        self.actions = []
        self._action_map = {}
        self.statevars = {}
        self._log = _getLogger('SERVICE')

        self._log.debug('%s url_base: %s' % (self.service_id, self._url_base))
        self._log.debug('%s SCPDURL: %s' % (self.service_id, self._scpd_url))
        self._log.debug('%s controlURL: %s' % (self.service_id, self._control_url))
        self._log.debug('%s eventSubURL: %s' % (self.service_id, self._event_sub_url))
        DEBUG('SERVICE INIT\n')
        DEBUG('%s url_base: %s\n' % (self.service_id, self._url_base))
        DEBUG('%s SCPDURL: %s\n' % (self.service_id, self._scpd_url))
        DEBUG('%s controlURL: %s\n' % (self.service_id, self._control_url))
        DEBUG('%s eventSubURL: %s\n' % (self.service_id, self._event_sub_url))

        # FIXME: http://192.168.1.2:1780/InternetGatewayDevice.xml/x_layer3forwarding.xml
        self._log.info('Reading %s' % (urljoin(self._url_base, self._scpd_url)))
        response = urllib2.urlopen(urljoin(self._url_base, self._scpd_url))
        DEBUG('SERVICE RESPONSE: (%s)\n' % response)
        raw_xml = response.read()
        DEBUG('SERVICE XML: (%s)\n' % raw_xml)
        self.scpd_xml = xml.dom.minidom.parseString(raw_xml)
        response.close()

        self._readStateVariables()
        self._readActions()

    def _readStateVariables(self):
        for statevar_node in self.scpd_xml.getElementsByTagName('stateVariable'):
            statevar_name = _XMLGetNodeText(statevar_node.getElementsByTagName('name')[0])
            statevar_datatype = _XMLGetNodeText(statevar_node.getElementsByTagName('dataType')[0])
            statevar_allowed_values = []

            for allowed_node in statevar_node.getElementsByTagName('allowedValueList'):
                for allowed_value_node in allowed_node.getElementsByTagName('allowedValue'):
                    statevar_allowed_values.append(_XMLGetNodeText(allowed_value_node))
            self.statevars[statevar_name] = {
                'name': statevar_name,
                'datatype': statevar_datatype,
                'allowed_values': statevar_allowed_values,
            }

    def _readActions(self):
        action_url = urljoin(self._url_base, self._control_url)
        for action_node in self.scpd_xml.getElementsByTagName('action'):
            name = _XMLGetNodeText(action_node.getElementsByTagName('name')[0])
            argsdef_in = []
            argsdef_out = []
            for arg_node in action_node.getElementsByTagName('argument'):
                arg_name = _XMLGetNodeText(arg_node.getElementsByTagName('name')[0])
                arg_dir = _XMLGetNodeText(arg_node.getElementsByTagName('direction')[0])
                arg_statevar = self.statevars[
                    _XMLGetNodeText(arg_node.getElementsByTagName('relatedStateVariable')[0])
                ]
                if arg_dir == 'in':
                    argsdef_in.append( (arg_name, arg_statevar) )
                else:
                    argsdef_out.append( (arg_name, arg_statevar) )
            action = Action(action_url, self.service_type, name, argsdef_in, argsdef_out)
            self._action_map[name] = action
            self.actions.append(action)

    def find_action(self, action_name):
        if action_name in self._action_map:
            return(self._action_map[action_name])
        return(None)

    # FIXME: Maybe move this?
    @staticmethod
    def marshall_from(datatype, value):
        dt_conv = {
            'ui1'         : lambda x: int(x),
            'ui2'         : lambda x: int(x),
            'ui4'         : lambda x: int(x),
            'i1'          : lambda x: int(x),
            'i2'          : lambda x: int(x),
            'i4'          : lambda x: int(x),
            'int'         : lambda x: int(x),
            'r4'          : lambda x: float(x),
            'r8'          : lambda x: float(x),
            'number'      : lambda x: float(x),
            'fixed'       : lambda x: float(x),
            'float'       : lambda x: float(x),
            'char'        : lambda x: x,
            'string'      : lambda x: x,
            'date'        : Exception,
            'dateTime'    : Exception,
            'dateTime.tz' : Exception,
            'boolean'     : lambda x: bool(x),
            'bin.base64'  : lambda x: x,
            'bin.hex'     : lambda x: x,
            'uri'         : lambda x: x,
            'uuid'        : lambda x: x,
        }
        return(dt_conv[datatype](value))

    def call(self, action_name, args={}, **kwargs):
        """Directly call an action
        Convenience method for quickly finding and calling an Action on a
        Service.
        """
        args = args.copy()
        if kwargs:
            # Allow both a dictionary of arguments and normal named arguments
            args.update(kwargs)

        action = self.find_action(action_name)
        if action:
            return(action.call(args))
        return(None)

    def __repr__(self):
        return("<Service service_id='%s'>" % (self.service_id))

class Action(object):
    def __init__(self, url, service_type, name, argsdef_in={}, argsdef_out={}):
        self.url = url
        self.service_type = service_type
        self.name = name
        self.argsdef_in = argsdef_in
        self.argsdef_out = argsdef_out
        self._log = _getLogger('ACTION')

    def call(self, args={}, **kwargs):
        args = args.copy()
        if kwargs:
            # Allow both a dictionary of arguments and normal named arguments
            args.update(kwargs)

        # Validate arguments using the SCPD stateVariable definitions
        for name, statevar in self.argsdef_in:
            if not name in args:
                raise UPNPError('Missing required param \'%s\'' % (name))
            self._validate_arg(name, args[name], statevar)

        # Make the actual call
        DEBUG('SOAP CALL: (%s) (%s) (%s) (%s)\n' % (self.name, args, self.url, self.service_type))
        soap_client = SOAP(self.url, self.service_type)
        soap_response = soap_client.call(self.name, args)

        # Marshall the response to python data types
        out = {}
        for name, statevar in self.argsdef_out:
            out[name] = Service.marshall_from(statevar['datatype'], soap_response[name])

        return(out)

    def _validate_arg(self, name, arg, argdef):
        """
        Validate and convert an incoming (unicode) string argument according
        the UPnP spec. Raises UPNPError.
        """
        datatype = argdef['datatype']
        try:
            if datatype == 'ui1':
                v = int(arg); assert v >= 0 and v <= 255
            elif datatype == 'ui2':
                v = int(arg); assert v >= 0 and v <= 65535
            elif datatype == 'ui4' :
                v = int(arg); assert v >= 0 and v <= 4294967295
            if datatype == 'i1':
                v = int(arg); assert v >= -128 and v <= 127
            elif datatype == 'i2':
                v = int(arg); assert v >= -32768 and v <= 32767
            elif datatype in ['i4', 'int']:
                v = int(arg);
            elif datatype == 'r4':
                v = float(arg); assert v >= 1.17549435E-38 and v <= 3.40282347E+38
            elif datatype in ['r8', 'number', 'float', 'fixed.14.4'] :
                v = float(arg); # r8 is too big for python, so we don't check anything
            elif datatype == 'char':
                v = arg.decode('utf8'); assert len(v) == 1
            elif datatype == 'string':
                v = arg.decode('utf8');
                if argdef['allowed_values'] and not v in argdef['allowed_values']:
                    raise UPNPError('Value \'%s\' not allowed for param \'%s\'' % (arg, name))
            elif datatype == 'date':
                v = arg # FIXME
            elif datatype == 'dateTime':
                v = arg # FIXME
            elif datatype == 'dateTime.tz':
                v = arg # FIXME
            elif datatype == 'time':
                v = arg # FIXME
            elif datatype == 'time.tz':
                v = arg # FIXME
            elif datatype == 'boolean':
                if arg.lower() in ['true', 'yes']:
                    v = 1
                elif arg.lower() in ['false', 'no']:
                    v = 0
                v = [0, 1][bool(arg)]
            elif datatype == 'bin.base64':
                v = arg # FIXME
            elif datatype == 'bin.hex':
                v = arg # FIXME
            elif datatype == 'uri':
                v = arg # FIXME
            elif datatype == 'uuid':
                v = arg # FIXME
        except Exception:
            raise UPNPError("%s should be of type '%s'" % (name, datatype))
        return(v)

    def __repr__(self):
        return("<Action '%s'>" % (self.name))

class SOAPError(Exception):
    pass

class SOAP(object):
    """SOAP (Simple Object Access Protocol) implementation
    This class defines a simple SOAP client.
    """
    def __init__(self, url, service_type):
        self.url = url
        self.service_type = service_type
        self._host = self.url.split('//', 1)[1].split('/', 1)[0] # Get hostname portion of url
        self._log = _getLogger('SOAP')


    def call(self, action_name, arg_in={}, debug=False):
        arg_values = '\n'.join( ['<%s>%s</%s>' % (k, v, k) for k, v in arg_in.items()] )
        body = \
            '<?xml version="1.0"?>\n' \
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\n' \
            '  <SOAP-ENV:Body>\n' \
            '    <m:%(action_name)s xmlns:m="%(service_type)s">\n' \
            '      %(arg_values)s\n' \
            '    </m:%(action_name)s>\n' \
            '   </SOAP-ENV:Body>\n' \
            '</SOAP-ENV:Envelope>\n' % {
                'action_name': action_name,
                'service_type': self.service_type,
                'arg_values': arg_values,
            }
        headers = {
            'SOAPAction': '"%s#%s"' % (self.service_type, action_name),
            'Host': self._host,
            'Content-Type': 'text/xml',
            'Content-Length': len(body),
        }

        # Uncomment this for debugging.
        # urllib2.install_opener(urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1)))
        DEBUG('ACTION CALL: (%s) (%s) (%s)\n' % (self.url, body, headers))
        request = urllib2.Request(self.url, body, headers)
        try:
            response = urllib2.urlopen(request)
            DEBUG('ACTION RESPONSE: (%s)\n' % response)
        except urllib2.HTTPError, e:
            raw_xml = e.read()
            DEBUG('ACTION ERROR XML: (%s)\n' % raw_xml)
            soap_error_xml = xml.dom.minidom.parseString(raw_xml)
            raise SOAPError(
                int(_XMLGetNodeText(soap_error_xml.getElementsByTagName('errorCode')[0])),
                _XMLGetNodeText(soap_error_xml.getElementsByTagName('errorDescription')[0]),
            )

        raw_xml = response.read()
        DEBUG('ACTION XML: (%s)\n' % raw_xml)
        contents = xml.dom.minidom.parseString(raw_xml)
        response.close()

        params_out = {}
        for node in contents.getElementsByTagName('*'):
            if node.localName.lower().endswith('response'):
                for param_out_node in node.childNodes:
                    if param_out_node.nodeType == param_out_node.ELEMENT_NODE:
                        params_out[param_out_node.localName] = _XMLGetNodeText(param_out_node)

        return(params_out)

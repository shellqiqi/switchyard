import sys
import os
import os.path
import unittest
import copy
import time

from switchyard.lib.testing import *
from switchyard.lib.address import *
from switchyard.lib.packet import *
from switchyard.lib.logging import setup_logging
from switchyard.lib.exceptions import *


class SrpyMatcherTest(unittest.TestCase):
    def testExactMatch0(self):
        pkt = Ethernet() + Arp()
        matcher = ExactMatch(pkt)
        self.assertTrue(matcher.match(pkt))
        pkt[0].src = '00:00:00:00:01:01'
        self.assertFalse(matcher.match(pkt))

    def testExactMatch1(self):
        pkt = Ethernet() + Arp()
        matcher = PacketMatcher(pkt, exact=True)
        self.assertTrue(matcher.match(pkt))

    def testExactMatch2(self):
        pkt = Ethernet() + IPv4() + ICMP()
        matcher = PacketMatcher(pkt, exact=True)
        pkt[0].ethertype = EtherType.ARP
        self.assertRaises(TestScenarioFailure, matcher.match, pkt)

    def testWildcardMatch0(self):
        pkt = Ethernet() + IPv4()
        matcher = WildcardMatch(pkt, [])
        self.assertTrue(matcher.match(pkt))
        pkt[1].ipid = 100 # ipid isn't checked in wildcard match
        self.assertTrue(matcher.match(pkt))
        pkt[0].src = '01:02:03:04:05:06'
        self.assertFalse(matcher.match(pkt))
        matcher = WildcardMatch(pkt, ['dl_src'])
        self.assertTrue(matcher.match(pkt))
        self.assertTrue('dl_src' in str(matcher))
        with self.assertRaises(AttributeError):
            matcher.dl_src            
        self.assertEqual(matcher.nw_src, IPv4Address("0.0.0.0"))
        self.assertEqual(matcher.dl_type, EtherType.IP)
        
    def testWildcardMatch1(self):
        pkt = Ethernet() + IPv4()
        matcher = PacketMatcher(pkt, exact=False)
        self.assertTrue(matcher.match(pkt))

    def testPredicateMatch1(self):
        pkt = Ethernet() + IPv4()
        matcher = PacketMatcher(pkt, '''lambda pkt: pkt[0].src == '00:00:00:00:00:00' ''', exact=False)
        self.assertTrue(matcher.match(pkt))

    def testPredicateMatch2(self):
        pkt = Ethernet() + IPv4()
        matcher = PacketMatcher(pkt, '''lambda pkt: pkt[0].src == '00:00:00:00:00:01' ''', exact=False)
        with self.assertRaises(TestScenarioFailure):
            matcher.match(pkt)

    def testPredicateMatch3(self):
        pkt = Ethernet() + IPv4()
        matcher = PacketMatcher(pkt, 
            '''lambda pkt: pkt[0].src == '00:00:00:00:00:00' ''', 
            '''lambda pkt: isinstance(pkt[1], IPv4) and pkt[1].ttl == 0''',
            exact=False)
        self.assertTrue(matcher.match(pkt))

    def testPredicateMatch4(self):
        pkt = Ethernet() + IPv4()
        matcher = PacketMatcher(pkt, 
            '''lambda pkt: pkt[0].src == '00:00:00:00:00:00' ''',
            '''lambda pkt: isinstance(pkt[1], IPv4) and pkt[1].ttl == 0''',
            exact=False)        
        self.assertTrue(matcher.match(pkt))

    def testPredicateMatch5(self):
        pkt = Ethernet() + IPv4()
        with self.assertRaises(Exception):
            matcher = PacketMatcher(pkt, list(), exact=False)

    def testPredicateMatch6(self):
        pkt = Ethernet() + IPv4()
        with self.assertRaises(Exception):
            matcher = PacketMatcher(pkt, 'not a function', exact=False)

    def testWildcarding(self):
        pkt = Ethernet() + IPv4()
        pkt[1].srcip = IPAddr("192.168.1.1")
        pkt[1].dstip = IPAddr("192.168.1.2")
        pkt[1].ttl = 64
        
        matcher = PacketMatcher(pkt, wildcard=['dl_dst', 'nw_dst'], exact=False)
        pkt[0].dst = "11:11:11:11:11:11"
        pkt[1].dstip = "192.168.1.3"
        self.assertTrue(matcher.match(copy.deepcopy(pkt)))

    def testWildcarding2(self):
        pkt = create_ip_arp_request('11:22:33:44:55:66', '192.168.1.1', '192.168.10.10')
        xcopy = copy.deepcopy(pkt)
        pkt[1].targethwaddr = '00:ff:00:ff:00:ff'
        matcher = PacketMatcher(pkt, wildcard=['arp_tha'], exact=False)
        self.assertTrue(matcher.match(xcopy))

        with self.assertRaises(TestScenarioFailure):
            pkt[1].senderhwaddr = '00:ff:00:ff:00:ff'
            matcher = PacketMatcher(pkt, wildcard=['arp_tha'], exact=False)
            matcher.match(xcopy)

    def testWildcardMatchOutput(self):
        pkt = create_ip_arp_request('11:22:33:44:55:66', '192.168.1.1', '192.168.10.10')
        outev = PacketOutputEvent("eth1", pkt, wildcard=('arp_tha',), exact=False)
        self.assertNotIn("IPv4", str(outev))
        rv = outev.match(SwitchyTestEvent.EVENT_OUTPUT, device='eth1', packet=pkt)
        self.assertEqual(rv, SwitchyTestEvent.MATCH_SUCCESS)

        outev = PacketOutputEvent("eth1", pkt, wildcard=('arp_tha',), exact=False)
        pktcopy = copy.deepcopy(pkt)
        pktcopy[1].targethwaddr = '00:ff:00:ff:00:ff'
        rv = outev.match(SwitchyTestEvent.EVENT_OUTPUT, device='eth1', packet=pktcopy)
        self.assertEqual(rv, SwitchyTestEvent.MATCH_SUCCESS)

        outev = PacketOutputEvent("eth1", pkt, wildcard=('arp_tha','dl_src'), exact=False)
        with self.assertRaises(TestScenarioFailure) as exc:
            pktcopy[1].senderhwaddr = '00:ff:00:ff:00:ff'
            rv = outev.match(SwitchyTestEvent.EVENT_OUTPUT, device='eth1', packet=pktcopy)
        self.assertNotIn("IPv4", str(exc.exception))

        p = Ethernet() + \
            IPv4(protocol=IPProtocol.UDP,src="1.2.3.4",dst="5.6.7.8") + \
            UDP(srcport=9999, dstport=4444)
        xcopy = copy.copy(p)
        outev = PacketOutputEvent("eth1", p, wildcard=('tp_src'), exact=False)
        with self.assertRaises(TestScenarioFailure) as exc:
            xcopy[2].dstport = 5555
            rv = outev.match(SwitchyTestEvent.EVENT_OUTPUT, device='eth1', packet=xcopy)
        estr = str(exc.exception)        
        self.assertIn("UDP *->4444", estr)


if __name__ == '__main__':
    setup_logging(False)
    unittest.main()

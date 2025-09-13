package network

import (
	"net"
	"runtime/debug"
	"testing"
)

// assert Fatal
func assert(t *testing.T, res bool, format string, a ...any) {
	if !res {
		t.Log(string(debug.Stack()))
		t.Fatalf(format, a...)
	}
}

func TestFcNetwork(t *testing.T) {
	_, ipnet, _ := net.ParseCIDR("10.140.0.0/16")
	var fcNets []*NetworkEnv
	for i := 0; i < 5000; i++ {
		netEnv := NewNetworkEnv(i, ipnet)
		fcNets = append(fcNets, &netEnv)
	}

	hostClonedIps := make(map[string]struct{})
	vethIps := make(map[string]struct{})
	// we want to make sure that their ip address is valid and not equal
	for _, n := range fcNets {
		// veth
		cidr := n.VethCIDR()
		ip := cidr.IP.To4()
		assert(t, ip[3] < 255 && ip[3] > 0, "veth ip %s out of range", ip.String())
		vip := n.VethIP()
		assert(t, vip.Equal(ip), "veth ip %s not consistent with veth cidr %s", vip.String(), cidr)
		assert(t, cidr.Contains(ip), "ip address %s, cidr %s", ip.String(), cidr.String())
		vipString := vip.String()
		// make sure vip not conflict with others
		_, ok := vethIps[vipString]
		assert(t, !ok, "duplicated veth ip address %s", vipString)
		// make sure ip is not in the same subnetwork
		for otherIp := range vethIps {
			assert(t, otherIp != vipString, "duplicated veth ip %s", vipString)
		}
		vethIps[vipString] = struct{}{}

		// host cloned ip
		hostCIDR := n.HostClonedCIDR()
		hostIp := hostCIDR.IP.To4()
		assert(t, hostIp[3] < 255 && hostIp[3] > 0, "host ip %s is out of range", hostIp.String())
		hIp := n.HostClonedIP()
		assert(t, hIp.Equal(hostIp), "host ip %s not consistent with host cloned cidr %s", hIp, hostCIDR)
		_, ok = hostClonedIps[hIp.String()]
		assert(t, !ok, "")

		hipString := hIp.String()
		for otherIp := range hostClonedIps {
			assert(t, hipString != otherIp, "duplicated host cloned ip %s", hIp)
		}
		hostClonedIps[hipString] = struct{}{}
	}
}

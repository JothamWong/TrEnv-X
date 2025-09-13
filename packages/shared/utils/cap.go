package utils

import (
	"fmt"

	"golang.org/x/sys/unix"
)

func RaiseAmbientCaps(caps []uintptr) error {
	var (
		hdr = unix.CapUserHeader{
			Version: unix.LINUX_CAPABILITY_VERSION_3,
		}
		data      unix.CapUserData
		updateCap bool
	)
	// The inheritable cap set of a running process cannot be changed
	// (i.e., only inherited from parent process).
	// But the PR_CAP_AMBIENT_RAISE needs the cap to be present in both
	// permitted and inheritable cap sets.
	// Thus, we manually set the inheritable and permitted cap set here.
	if err := unix.Capget(&hdr, &data); err != nil {
		return fmt.Errorf("error getting capabilities: %w", err)
	}
	for _, capability := range caps {
		if (1<<capability)&data.Inheritable == 0 {
			updateCap = true
		}
		data.Inheritable |= (1 << capability)
		if (1<<capability)&data.Permitted == 0 {
			updateCap = true
		}
		data.Permitted |= (1 << capability)
	}
	if updateCap {
		if err := unix.Capset(&hdr, &data); err != nil {
			return fmt.Errorf("error setting capabilities: %w", err)
		}
	}

	for _, capability := range caps {
		if err := unix.Prctl(unix.PR_CAP_AMBIENT, unix.PR_CAP_AMBIENT_RAISE, capability, 0, 0); err != nil {
			return fmt.Errorf("error raising ambient capability %d: %w", capability, err)
		}
	}
	return nil
}

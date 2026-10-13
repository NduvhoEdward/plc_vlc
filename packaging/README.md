# Portable PC launchers

Windows x64 launcher source for the private sender and receiver packages. Each package bundles the verified official Python 3.13.16 embeddable runtime, pyserial 3.5 and websockets 15.0.1. Credentials and generated ZIPs stay outside this repository.

START.cmd opens the local status dashboard and supervises the bridge. RX selection requires an RX STAT signature. Sender Ethernet setup adds the dedicated HomePlug address only when the existing wired subnet is unsuitable; it saves DHCP configuration and includes a restore helper. No default gateway is added. Firmware is unchanged.

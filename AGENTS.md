# Mobile PLC/VLC connection safeguards

Read [SYSTEM-CONTEXT.md](SYSTEM-CONTEXT.md) before modifying bridges, launchers, dashboard integration, website live controls or packages.
The user explicitly requires the original text_image_vlc_dashboard receiver GUI and preservation of TX/mobile connections.
One sender relay owner; one receiver relay/USB owner. Dashboard observes local /events and never opens RX USB in mobile mode.
Preserve firmware, AUTO/75% gate, board rates and actual-reception verification. Do not replay transfers or run a second producer.
Never commit credentials or private packages. Build packages into a new directory while one is running.
Keep original dashboard base modules as an unchanged snapshot; implement mobile integration in adapter modules.

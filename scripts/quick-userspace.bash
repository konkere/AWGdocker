# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 Konkere
# AWGdocker: force userspace even when the host has an AmneziaWG kernel module.
add_if() {
    cmd "${WG_QUICK_USERSPACE_IMPLEMENTATION:-amneziawg-go}" "$INTERFACE"
}

#!/usr/bin/env bash
# Worktree port allocation for Kind clusters.
# Manages slots 1-3, each with a fixed port offset.
#
# Slot 0: main checkout (8000/5173) — not managed here, uses kind-config.yaml
# Slot 1: 8010/5183
# Slot 2: 8020/5193
# Slot 3: 8030/5203
#
# Port scheme avoids compose ports (API=8001, UI=5173).
# Usage: source this file, then call get_worktree_slot / release_worktree_slot.

SLOT_DIR="${HOME}/.analysi/kind-slots"
MAX_SLOTS=3

# get_worktree_slot CLUSTER_NAME
# Returns slot number (1-3). Claims first free slot or reclaims stale ones.
# Exits with error if all slots are in use.
get_worktree_slot() {
    local cluster_name="${1:?cluster_name required}"
    mkdir -p "$SLOT_DIR"

    # Check if this cluster already has a slot
    for slot in $(seq 1 $MAX_SLOTS); do
        if [ -f "$SLOT_DIR/slot-${slot}" ] && [ "$(cat "$SLOT_DIR/slot-${slot}")" = "$cluster_name" ]; then
            echo "$slot"
            return 0
        fi
    done

    # Claim the first free slot (reclaim stale ones where cluster no longer exists)
    for slot in $(seq 1 $MAX_SLOTS); do
        if [ ! -f "$SLOT_DIR/slot-${slot}" ]; then
            echo "$cluster_name" > "$SLOT_DIR/slot-${slot}"
            echo "$slot"
            return 0
        fi
        local owner
        owner=$(cat "$SLOT_DIR/slot-${slot}")
        if ! kind get clusters 2>/dev/null | grep -q "^${owner}$"; then
            echo "$cluster_name" > "$SLOT_DIR/slot-${slot}"
            echo "$slot"
            return 0
        fi
    done

    echo "ERROR: All $MAX_SLOTS Kind cluster slots are in use." >&2
    echo "Active clusters:" >&2
    for slot in $(seq 1 $MAX_SLOTS); do
        [ -f "$SLOT_DIR/slot-${slot}" ] && echo "  Slot $slot: $(cat "$SLOT_DIR/slot-${slot}")" >&2
    done
    echo "Run 'make k8s-down' in an unused worktree first." >&2
    exit 1
}

# release_worktree_slot CLUSTER_NAME
# Releases the slot held by the given cluster.
release_worktree_slot() {
    local cluster_name="${1:?cluster_name required}"
    for slot in $(seq 1 $MAX_SLOTS); do
        if [ -f "$SLOT_DIR/slot-${slot}" ] && [ "$(cat "$SLOT_DIR/slot-${slot}")" = "$cluster_name" ]; then
            rm "$SLOT_DIR/slot-${slot}"
            return 0
        fi
    done
}

# ports_for_slot SLOT
# Sets API_HOST_PORT and UI_HOST_PORT for the given slot number.
ports_for_slot() {
    local slot="${1:?slot required}"
    API_HOST_PORT=$((8000 + slot * 10))
    UI_HOST_PORT=$((5173 + slot * 10))
}

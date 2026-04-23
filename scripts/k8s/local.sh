#!/usr/bin/env bash
# Local Kubernetes deployment using kind + Helm
# Usage: local.sh [up|down|status|logs|build|deploy]
#
# IMPORTANT: Images are built locally and loaded into kind via `kind load`.
# They are NEVER pushed to any registry from this script.
# Registry publishing is handled exclusively by CI/CD.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ──── Worktree-aware cluster naming ────────────────────
# Main checkout uses "analysi" with static kind-config.yaml.
# Worktrees get "analysi-<slug>" with dynamically allocated ports.
source "$SCRIPT_DIR/worktree-ports.sh"

if [ "$(git -C "$REPO_ROOT" rev-parse --git-dir 2>/dev/null)" != "$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)" ] 2>/dev/null; then
    IS_WORKTREE=1
    WORKTREE_SLUG=$(basename "$REPO_ROOT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | cut -c1-20)
    CLUSTER_NAME="analysi-${WORKTREE_SLUG}"
else
    IS_WORKTREE=0
    CLUSTER_NAME="analysi"
fi

KIND_CONFIG_STATIC="$REPO_ROOT/deployments/k8s/kind-config.yaml"
CHART_DIR="$REPO_ROOT/deployments/helm/analysi"
VALUES_FILE="$CHART_DIR/values/local.yaml"
NAMESPACE="default"
RELEASE_NAME="analysi"
KIND_NODE="${CLUSTER_NAME}-control-plane"

# Host ports — main uses kind-config.yaml, worktrees use slot-based allocation
if [ "$IS_WORKTREE" = "1" ]; then
    SLOT=$(get_worktree_slot "$CLUSTER_NAME")
    ports_for_slot "$SLOT"
else
    API_HOST_PORT=$(yq '.nodes[0].extraPortMappings[] | select(.containerPort == 30080) | .hostPort' "$KIND_CONFIG_STATIC")
    UI_HOST_PORT=$(yq '.nodes[0].extraPortMappings[] | select(.containerPort == 30173) | .hostPort' "$KIND_CONFIG_STATIC")
fi

# Generate kind config for worktrees (unique hostPorts per cluster)
get_kind_config() {
    if [ "$IS_WORKTREE" = "1" ]; then
        local tmpconfig
        tmpconfig=$(mktemp /tmp/kind-config-XXXXXX.yaml)
        cat > "$tmpconfig" <<KINDEOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: ${API_HOST_PORT}
        protocol: TCP
      - containerPort: 30173
        hostPort: ${UI_HOST_PORT}
        protocol: TCP
KINDEOF
        echo "$tmpconfig"
    else
        echo "$KIND_CONFIG_STATIC"
    fi
}

# Unified Analysi image — built locally, NEVER pushed to a public registry.
# All services (api, alerts-worker, integrations-worker) share this image;
# the entrypoint is configured at the Helm layer via command:.
APP_IMAGE="analysi/app:latest"
APP_DOCKERFILE="deployments/docker/Dockerfile"

# Custom PostgreSQL image with pg_partman + pg_cron (matches deps.yml build).
PG_IMAGE="analysi-postgres:15-partman"
PG_DOCKERFILE="deployments/docker/postgres/Dockerfile"

# UI image — built from the in-repo ui/ subproject.
# UI_REPO can be overridden to point elsewhere (e.g. a local fork) if needed.
UI_REPO="${UI_REPO:-$REPO_ROOT/ui}"
UI_DOCKERFILE="$REPO_ROOT/deployments/docker/ui/Dockerfile"
UI_IMAGE="analysi/ui:latest"

# Kind node image — override with KIND_NODE_IMAGE to use a locally cached version
# when the default (latest for your kind version) is slow to pull.
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-}"

# Dependency images — same official images as docker-compose (no bitnami).
# Pulled from public registries, loaded into kind.
DEP_IMAGES=(
    # postgres:15-alpine is NOT used directly — we build analysi-postgres:15-partman
    # (custom image with pg_partman + pg_cron) in cmd_build and load it separately.
    "valkey/valkey:8-alpine"
    "minio/minio:latest"
    "hashicorp/vault:1.17"
    "flyway/flyway:11"
    "busybox:1.37"
)

# ──── Helpers ────────────────────────────────────────────

check_prerequisites() {
    local missing=0
    for cmd in kind kubectl helm docker yq; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "ERROR: $cmd is required but not installed"
            missing=1
        fi
    done
    if [ $missing -eq 1 ]; then
        echo "Install missing tools and try again."
        exit 1
    fi
}

cluster_exists() {
    kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"
}

ensure_cluster() {
    if ! cluster_exists; then
        echo "Cluster '$CLUSTER_NAME' does not exist. Run: make k8s-up"
        return 1
    fi
    kubectl config use-context "kind-${CLUSTER_NAME}" &>/dev/null
}

# Load an image into kind using docker save pipe (workaround for ARM Macs
# where `kind load docker-image` fails with multi-platform images).
load_image_to_kind() {
    local image="$1"
    echo "  Loading $image..."
    docker save "$image" | docker exec -i "$KIND_NODE" \
        ctr --namespace=k8s.io images import - >/dev/null 2>&1
}

# ──── Preflight ─────────────────────────────────────────
# Validates that dependency images work on the host architecture and that
# every image referenced in Helm values is accounted for in DEP_IMAGES or
# built by cmd_build. Catches broken ARM images and Helm/script drift early.

cmd_preflight() {
    echo "Running preflight checks..."
    local failures=0

    # 1. Verify every DEP_IMAGE actually runs on this architecture.
    #    Catches images with wrong-arch binaries (e.g., flyway:11-alpine on ARM).
    echo ""
    echo "Checking dependency images run on $(uname -m)..."
    for image in "${DEP_IMAGES[@]}"; do
        # Pull if missing
        if ! docker image inspect "$image" &>/dev/null; then
            echo "  Pulling $image..."
            docker pull "$image" --quiet >/dev/null 2>&1 || true
        fi
        if ! docker image inspect "$image" &>/dev/null; then
            echo "  FAIL: $image — could not pull"
            failures=$((failures + 1))
            continue
        fi
        # Verify the image can execute on this architecture.
        # Use --entrypoint to bypass custom entrypoints (e.g., minio, flyway)
        # that reject unknown arguments. "echo ok" is universal.
        if ! docker run --rm --entrypoint sh "$image" -c "echo ok" >/dev/null 2>&1; then
            echo "  FAIL: $image — cannot execute (likely broken ARM build)"
            failures=$((failures + 1))
        else
            echo "  OK:   $image"
        fi
    done

    # 2. Cross-check Helm values vs what we load/build.
    #    Merges base values.yaml with local.yaml to get the effective image set,
    #    then verifies every image is in DEP_IMAGES or is a locally-built image.
    echo ""
    echo "Cross-checking Helm images vs local.sh..."

    # Images we build locally (not pulled from registries)
    local built_images=("$APP_IMAGE" "$PG_IMAGE" "$UI_IMAGE")

    # All images in DEP_IMAGES + built images (normalized to repo:tag)
    local known_images=()
    for img in "${DEP_IMAGES[@]}"; do
        known_images+=("$img")
    done
    for img in "${built_images[@]}"; do
        known_images+=("$img")
    done

    # Extract image references from effective Helm values (base + local overlay).
    # yq merge: local.yaml overrides values.yaml, then extract all image pairs.
    local merged_file
    merged_file=$(mktemp)
    trap 'rm -f "${merged_file:-}"' RETURN
    yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
        "$CHART_DIR/values.yaml" "$VALUES_FILE" > "$merged_file"

    # Collect disabled components so we can skip their images
    local disabled_components=()
    for component in postgresql valkey minio vault keycloak; do
        local enabled
        enabled=$(yq ".$component.enabled" "$merged_file")
        if [[ "$enabled" == "false" ]]; then
            disabled_components+=("$component")
        fi
    done

    local helm_images
    helm_images=$(yq eval '.. | select(has("repository") and has("tag")) | .repository + ":" + .tag' "$merged_file")

    while IFS= read -r helm_img; do
        [ -z "$helm_img" ] && continue
        # Skip images with empty tags (resolved at deploy time via Chart.AppVersion)
        [[ "$helm_img" == *":" ]] && continue
        # Skip images belonging to disabled components
        local skip=false
        local img_repo="${helm_img%%:*}"
        for comp in "${disabled_components[@]+"${disabled_components[@]}"}"; do
            local comp_repo
            comp_repo=$(yq ".$comp.image.repository // \"\"" "$merged_file")
            if [[ -n "$comp_repo" ]] && [[ "$img_repo" == "$comp_repo" ]]; then
                skip=true
                break
            fi
        done
        $skip && continue

        local found=false
        for known in "${known_images[@]}"; do
            if [[ "$known" == "$helm_img" ]]; then
                found=true
                break
            fi
        done
        if ! $found; then
            echo "  FAIL: Helm expects '$helm_img' but it's not in DEP_IMAGES or built locally"
            failures=$((failures + 1))
        else
            echo "  OK:   $helm_img"
        fi
    done <<< "$helm_images"

    echo ""
    if [ $failures -gt 0 ]; then
        echo "Preflight FAILED: $failures issue(s) found. Fix before proceeding."
        return 1
    fi
    echo "Preflight passed."
}

# ──── Commands ───────────────────────────────────────────

cmd_up() {
    check_prerequisites

    # 0. Preflight — catch broken images and Helm drift early
    cmd_preflight || exit 1

    # 1. Create cluster if needed
    if cluster_exists; then
        echo "Cluster '$CLUSTER_NAME' already exists"
    else
        local kind_config
        kind_config=$(get_kind_config)
        echo "Creating kind cluster '$CLUSTER_NAME'..."
        echo "  API port: ${API_HOST_PORT}  UI port: ${UI_HOST_PORT}"
        local kind_args=(create cluster --name "$CLUSTER_NAME" --config "$kind_config")
        if [ -n "$KIND_NODE_IMAGE" ]; then
            echo "  Using node image: $KIND_NODE_IMAGE"
            kind_args+=(--image "$KIND_NODE_IMAGE")
        fi
        kind "${kind_args[@]}"
        # Clean up temp config for worktrees
        [ "$IS_WORKTREE" = "1" ] && rm -f "$kind_config"
    fi

    # 2. Pull and load dependency images
    cmd_load_deps

    # 3. Build + load app images
    cmd_build

    # 4. Deploy with Helm
    cmd_deploy

    echo ""
    echo "API accessible at: http://localhost:${API_HOST_PORT}"
    echo "Health check:      curl http://localhost:${API_HOST_PORT}/healthz"
}

cmd_load_deps() {
    check_prerequisites
    ensure_cluster || exit 1

    echo "Pulling and loading dependency images..."
    for image in "${DEP_IMAGES[@]}"; do
        # Pull if not already local
        if ! docker image inspect "$image" &>/dev/null; then
            echo "  Pulling $image..."
            docker pull "$image" --quiet
        fi
        load_image_to_kind "$image"
    done
    echo "Dependency images loaded."
}

cmd_build() {
    check_prerequisites
    ensure_cluster || exit 1

    echo "Building production image..."
    echo "  Building $APP_IMAGE..."
    docker build -t "$APP_IMAGE" \
        --target production \
        -f "$REPO_ROOT/$APP_DOCKERFILE" \
        "$REPO_ROOT" \
        --quiet

    # Build UI image (from separate repo) — production nginx build
    if [[ -d "$UI_REPO" ]]; then
        echo "  Building $UI_IMAGE (nginx production)..."
        docker build -t "$UI_IMAGE" \
            --target production \
            --build-arg VITE_BACKEND_API_URL=http://localhost:${API_HOST_PORT} \
            --build-arg VITE_DISABLE_AUTH=true \
            --build-arg VITE_E2E_API_KEY=dev-admin-api-key \
            -f "$UI_DOCKERFILE" \
            "$UI_REPO" \
            --quiet
    else
        echo "  SKIP: UI sources not found at $UI_REPO"
    fi

    # Build custom PostgreSQL with pg_partman + pg_cron
    echo "  Building $PG_IMAGE..."
    docker build -t "$PG_IMAGE" \
        --build-arg PG_MAJOR=15 \
        -f "$REPO_ROOT/$PG_DOCKERFILE" \
        "$REPO_ROOT/deployments/docker/postgres" \
        --quiet

    echo ""
    echo "Loading images into kind cluster..."
    load_image_to_kind "$APP_IMAGE"
    load_image_to_kind "$PG_IMAGE"
    if docker image inspect "$UI_IMAGE" &>/dev/null; then
        load_image_to_kind "$UI_IMAGE"
    fi

    echo "Images built and loaded."
}

cmd_deploy() {
    check_prerequisites
    ensure_cluster || exit 1

    # Create/update ConfigMap with Flyway SQL migrations
    echo "Loading Flyway SQL migrations..."
    kubectl delete configmap flyway-sql -n "$NAMESPACE" 2>/dev/null || true
    kubectl create configmap flyway-sql \
        --from-file="$REPO_ROOT/migrations/flyway/sql/" \
        -n "$NAMESPACE"

    if helm status "$RELEASE_NAME" -n "$NAMESPACE" &>/dev/null; then
        echo "Upgrading Helm release '$RELEASE_NAME'..."
        helm upgrade "$RELEASE_NAME" "$CHART_DIR" \
            -n "$NAMESPACE" \
            -f "$VALUES_FILE" \
            --wait --timeout 10m
    else
        echo "Installing Helm release '$RELEASE_NAME'..."
        helm install "$RELEASE_NAME" "$CHART_DIR" \
            -n "$NAMESPACE" \
            -f "$VALUES_FILE" \
            --wait --timeout 10m
    fi

    echo ""
    echo "Deployment complete!"
    echo ""
    cmd_status
}

cmd_down() {
    check_prerequisites

    if ! cluster_exists; then
        echo "Cluster '$CLUSTER_NAME' does not exist"
        return 0
    fi

    echo "Deleting kind cluster '$CLUSTER_NAME'..."
    kind delete cluster --name "$CLUSTER_NAME"
    release_worktree_slot "$CLUSTER_NAME"
    echo "Cluster deleted."
}

cmd_status() {
    ensure_cluster || return 1

    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║                    Analysi K8s Status                           ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo ""

    # Pod status with color coding
    kubectl get pods -n "$NAMESPACE" --no-headers \
        -o custom-columns='NAME:.metadata.name,STATUS:.status.phase,READY:.status.conditions[?(@.type=="Ready")].status,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp' 2>/dev/null | \
    awk '{
        name=$1; status=$2; ready=$3; restarts=$4;
        # Simplify name: drop "analysi-analysi-" or "analysi-" prefix
        gsub(/^analysi-analysi-/, "", name);
        gsub(/^analysi-/, "", name);
        # Truncate flyway job suffix
        if (name ~ /^flyway-/) { name = "flyway (job)" }
        # Status icon
        if (status == "Running" && ready == "True") {
            icon="\033[32m✅ Running\033[0m"
        } else if (status == "Succeeded") {
            icon="\033[32m✅ Completed\033[0m"
        } else {
            icon="\033[31m❌ " status "\033[0m"
        }
        printf "  %-40s %s\n", name, icon
    }'

    echo ""
    echo "──────────────────────────────────────────────────────────────────────"
    echo "  API: http://localhost:${API_HOST_PORT}"
    echo "  UI:  http://localhost:${UI_HOST_PORT}"
    echo ""
    echo "  Quick Commands:"
    echo "    make k8s-verify              Check health"
    echo "    make k8s-logs SERVICE=api    Tail logs"
    echo "    make k8s-deploy              Helm upgrade"
    echo "    make k8s-build               Rebuild images"
}

cmd_logs() {
    ensure_cluster || return 1

    local service="${1:-}"
    if [ -n "$service" ]; then
        kubectl logs -n "$NAMESPACE" -l "app.kubernetes.io/component=$service" --tail=100 -f
    else
        kubectl logs -n "$NAMESPACE" -l "app.kubernetes.io/name=analysi" --tail=50 --all-containers
    fi
}

# ──── Main ───────────────────────────────────────────────

case "${1:-help}" in
    up)         cmd_up ;;
    down)       cmd_down ;;
    build)      cmd_build ;;
    deploy)     cmd_deploy ;;
    preflight)  cmd_preflight ;;
    status)     cmd_status ;;
    logs)       cmd_logs "${2:-}" ;;
    *)
        echo "Usage: $0 {up|down|build|deploy|preflight|status|logs [service]}"
        echo ""
        echo "Commands:"
        echo "  up         Create cluster + build + load deps + deploy (full setup)"
        echo "  build      Build app image and load into kind"
        echo "  deploy     Helm install/upgrade only (fast, no image rebuild)"
        echo "  preflight  Validate images work on this arch + match Helm values"
        echo "  down       Delete kind cluster"
        echo "  status     Show pod/service status"
        echo "  logs       Tail logs (optionally: api, alerts-worker, integrations-worker)"
        exit 1
        ;;
esac

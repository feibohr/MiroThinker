#!/bin/bash
#
# Build and push MiroThinker Docker images for Kubernetes
# Customized for your K8s environment
#
# Usage:
#   ./build-k8s.sh [TAG] [TARGET]
#   
#   TAG:    Image tag (default: current date YYYYMMDD)
#   TARGET: What to build - 'api', 'web', or 'all' (default: all)
#
# Examples:
#   ./build-k8s.sh                    # Build all with date tag
#   ./build-k8s.sh 20260120           # Build all with custom tag
#   ./build-k8s.sh 20260120 api       # Build only API server
#   ./build-k8s.sh 20260120 web       # Build only Gradio web
#

set -e

# Configuration from your k8s deployment files
API_REGISTRY="192.168.16.55/aigc"
WEB_REGISTRY="192.168.16.55/aigc"

# Parse arguments
TAG=${1:-$(date +%Y%m%d)}
TARGET=${2:-"all"}

# Validate target
if [[ ! "$TARGET" =~ ^(api|web|all)$ ]]; then
    echo "❌ Invalid target: $TARGET"
    echo "   Valid targets: api, web, all"
    exit 1
fi

echo "🏗️  Building MiroThinker images for Kubernetes..."
echo "   Registry: ${API_REGISTRY}"
echo "   Tag: ${TAG}"
echo "   Target: ${TARGET}"
echo ""

# Build and push API Server
if [[ "$TARGET" == "api" || "$TARGET" == "all" ]]; then
    echo "📦 Building API Server..."
    docker build \
        --no-cache \
        -f apps/api-server/Dockerfile \
        -t ${API_REGISTRY}/mirothinker-api:${TAG} \
        .
    
    echo "📤 Pushing API Server to registry..."
    docker push ${API_REGISTRY}/mirothinker-api:${TAG}
    echo "✅ API Server: ${API_REGISTRY}/mirothinker-api:${TAG}"
    echo ""
fi

# Build and push Gradio Web
if [[ "$TARGET" == "web" || "$TARGET" == "all" ]]; then
    echo "📦 Building Gradio Web..."
    docker build \
        -f apps/gradio-demo/Dockerfile \
        -t ${WEB_REGISTRY}/mirothinker-web:${TAG} \
        .
    
    echo "📤 Pushing Gradio Web to registry..."
    docker push ${WEB_REGISTRY}/mirothinker-web:${TAG}
    echo "✅ Gradio Web: ${WEB_REGISTRY}/mirothinker-web:${TAG}"
    echo ""
fi

echo "🎉 Done!"
echo ""
echo "📝 Images ready for deployment:"
if [[ "$TARGET" == "api" || "$TARGET" == "all" ]]; then
    echo "   API Server: ${API_REGISTRY}/mirothinker-api:${TAG}"
fi
if [[ "$TARGET" == "web" || "$TARGET" == "all" ]]; then
    echo "   Gradio Web: ${WEB_REGISTRY}/mirothinker-web:${TAG}"
fi
echo ""
echo "💡 To deploy to Kubernetes:"
echo "   cd k8s"
echo "   kubectl apply -f ."


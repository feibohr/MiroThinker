#!/bin/bash
#
# Build and push MiroThinker Docker images for Kubernetes
# Customized for your K8s environment
#

set -e

# Configuration from your k8s deployment files
API_REGISTRY="192.168.16.55/aigc"
WEB_REGISTRY="192.168.16.55/aigc"
TAG=${1:-"20260116"}

echo "🏗️  Building MiroThinker images for Kubernetes..."
echo "   API Server: ${API_REGISTRY}/mirothinker-api:${TAG}"
echo "   Gradio Web: ${WEB_REGISTRY}/mirothinker-web:${TAG}"
echo ""

# Build API Server
echo "📦 Building API Server..."
docker build \
    -f apps/api-server/Dockerfile \
    -t ${API_REGISTRY}/mirothinker-api:${TAG} \
    .

# Build Gradio Web
echo "📦 Building Gradio Web..."
docker build \
    -f apps/gradio-demo/Dockerfile \
    -t ${WEB_REGISTRY}/mirothinker-web:${TAG} \
    .

echo ""
echo "✅ Build completed successfully!"
echo ""

# Ask for confirmation before pushing
read -p "🚀 Push images to registry? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📤 Pushing API Server to ${API_REGISTRY}..."
    docker push ${API_REGISTRY}/mirothinker-api:${TAG}
    
    echo "📤 Pushing Gradio Web to ${WEB_REGISTRY}..."
    docker push ${WEB_REGISTRY}/mirothinker-web:${TAG}
    
    echo ""
    echo "✅ All images pushed successfully!"
    echo ""
    echo "📝 Images ready for deployment:"
    echo "   API Server: ${API_REGISTRY}/mirothinker-api:${TAG}"
    echo "   Gradio Web: ${WEB_REGISTRY}/mirothinker-web:${TAG}"
else
    echo "⏭️  Push cancelled"
fi

echo ""
echo "🎉 Done!"
echo ""
echo "💡 To deploy to Kubernetes:"
echo "   cd k8s"
echo "   kubectl apply -f ."


#!/bin/bash

# Docker automation script for Flask Webhook Viewer

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DOCKER_IMAGE_NAME="bdgtest/flask-webhook-viewer"
DOCKER_CONTAINER_NAME="flask-webhook-viewer"
DOCKER_PORT=8000

# Function to display usage/help message
show_help() {
    echo -e "${BLUE}Flask Webhook Viewer Docker Script${NC}"
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  build       - Build the Docker image"
    echo "  run         - Run the Docker container"
    echo "  start       - Start an existing container"
    echo "  stop        - Stop the running container"
    echo "  restart     - Restart the container"
    echo "  status      - Show container status"
    echo "  logs        - Show container logs"
    echo "  shell       - Get a shell inside the container"
    echo "  push        - Push image to Docker Hub (requires login)"
    echo "  pull        - Pull image from Docker Hub"
    echo "  clean       - Remove container and image"
    echo "  help        - Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  IMAGE_NAME  - Docker image name (default: $DOCKER_IMAGE_NAME)"
    echo "  CONTAINER   - Container name (default: $DOCKER_CONTAINER_NAME)"
    echo "  PORT        - Host port to expose (default: $DOCKER_PORT)"
    echo ""
}

# Function to build Docker image
build_image() {
    echo -e "${BLUE}Building Docker image ${DOCKER_IMAGE_NAME}...${NC}"
    docker build -t $DOCKER_IMAGE_NAME .
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Docker image built successfully!${NC}"
    else
        echo -e "${RED}Error building Docker image.${NC}"
        exit 1
    fi
}

# Function to run Docker container
run_container() {
    echo -e "${BLUE}Running Docker container ${DOCKER_CONTAINER_NAME}...${NC}"
    
    # Check if container already exists
    if docker ps -a | grep -q ${DOCKER_CONTAINER_NAME}; then
        echo -e "${YELLOW}Container ${DOCKER_CONTAINER_NAME} already exists.${NC}"
        echo -e "Use '${YELLOW}$0 start${NC}' to start it or '${YELLOW}$0 clean${NC}' to remove it first."
        return 1
    fi
    
    # Create data directory if it doesn't exist
    mkdir -p ./data
    
    # Run the container
    docker run -d \
        --name $DOCKER_CONTAINER_NAME \
        -p $DOCKER_PORT:8000 \
        -v $(pwd)/data:/app/data \
        --restart unless-stopped \
        $DOCKER_IMAGE_NAME
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Container is now running!${NC}"
        echo -e "Access the application at http://localhost:${DOCKER_PORT}"
    else
        echo -e "${RED}Failed to start container.${NC}"
        exit 1
    fi
}

# Function to start an existing container
start_container() {
    if docker ps -a | grep -q ${DOCKER_CONTAINER_NAME}; then
        echo -e "${BLUE}Starting container ${DOCKER_CONTAINER_NAME}...${NC}"
        docker start $DOCKER_CONTAINER_NAME
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Container started successfully!${NC}"
            echo -e "Access the application at http://localhost:${DOCKER_PORT}"
        else
            echo -e "${RED}Failed to start container.${NC}"
            exit 1
        fi
    else
        echo -e "${YELLOW}Container does not exist. Use '$0 run' to create and run it.${NC}"
        return 1
    fi
}

# Function to stop the container
stop_container() {
    if docker ps | grep -q ${DOCKER_CONTAINER_NAME}; then
        echo -e "${BLUE}Stopping container ${DOCKER_CONTAINER_NAME}...${NC}"
        docker stop $DOCKER_CONTAINER_NAME
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Container stopped successfully.${NC}"
        else
            echo -e "${RED}Failed to stop container.${NC}"
            exit 1
        fi
    else
        echo -e "${YELLOW}Container is not running.${NC}"
    fi
}

# Function to restart the container
restart_container() {
    echo -e "${BLUE}Restarting container ${DOCKER_CONTAINER_NAME}...${NC}"
    docker restart $DOCKER_CONTAINER_NAME
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Container restarted successfully!${NC}"
    else
        echo -e "${RED}Failed to restart container.${NC}"
        echo -e "Make sure the container exists with '$0 status'${NC}"
        exit 1
    fi
}

# Function to check container status
check_status() {
    echo -e "${BLUE}Checking status of ${DOCKER_CONTAINER_NAME}...${NC}"
    if docker ps -a | grep -q ${DOCKER_CONTAINER_NAME}; then
        docker ps -a | grep ${DOCKER_CONTAINER_NAME}
    else
        echo -e "${YELLOW}Container does not exist.${NC}"
    fi
}

# Function to view container logs
view_logs() {
    echo -e "${BLUE}Viewing logs for ${DOCKER_CONTAINER_NAME}...${NC}"
    if docker ps -a | grep -q ${DOCKER_CONTAINER_NAME}; then
        docker logs $DOCKER_CONTAINER_NAME
    else
        echo -e "${YELLOW}Container does not exist.${NC}"
    fi
}

# Function to get a shell inside the container
get_shell() {
    echo -e "${BLUE}Opening shell in ${DOCKER_CONTAINER_NAME}...${NC}"
    if docker ps | grep -q ${DOCKER_CONTAINER_NAME}; then
        docker exec -it $DOCKER_CONTAINER_NAME /bin/bash || docker exec -it $DOCKER_CONTAINER_NAME /bin/sh
    else
        echo -e "${YELLOW}Container is not running.${NC}"
        echo -e "Start it with '$0 start' first.${NC}"
    fi
}

# Function to push image to Docker Hub
push_image() {
    echo -e "${BLUE}Pushing ${DOCKER_IMAGE_NAME} to Docker Hub...${NC}"
    echo -e "${YELLOW}Make sure you are logged in with 'docker login'${NC}"
    docker push $DOCKER_IMAGE_NAME
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Image pushed successfully!${NC}"
    else
        echo -e "${RED}Failed to push image.${NC}"
        echo -e "Make sure you are logged in with 'docker login' and have permission to push to this repository.${NC}"
        exit 1
    fi
}

# Function to pull image from Docker Hub
pull_image() {
    echo -e "${BLUE}Pulling ${DOCKER_IMAGE_NAME} from Docker Hub...${NC}"
    docker pull $DOCKER_IMAGE_NAME
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Image pulled successfully!${NC}"
    else
        echo -e "${RED}Failed to pull image.${NC}"
        exit 1
    fi
}

# Function to clean up container and image
clean_up() {
    echo -e "${BLUE}Cleaning up Docker resources...${NC}"
    
    # Stop and remove container if it exists
    if docker ps -a | grep -q ${DOCKER_CONTAINER_NAME}; then
        echo -e "Removing container ${DOCKER_CONTAINER_NAME}..."
        docker stop $DOCKER_CONTAINER_NAME 2>/dev/null
        docker rm $DOCKER_CONTAINER_NAME
    fi
    
    # Remove image if it exists
    if docker images | grep -q ${DOCKER_IMAGE_NAME}; then
        echo -e "Removing image ${DOCKER_IMAGE_NAME}..."
        docker rmi $DOCKER_IMAGE_NAME
    fi
    
    echo -e "${GREEN}Cleanup complete.${NC}"
}

# Apply any environment variables that were passed
[ ! -z "$IMAGE_NAME" ] && DOCKER_IMAGE_NAME=$IMAGE_NAME
[ ! -z "$CONTAINER" ] && DOCKER_CONTAINER_NAME=$CONTAINER
[ ! -z "$PORT" ] && DOCKER_PORT=$PORT

# Process command line argument
case "$1" in
    build)
        build_image
        ;;
    run)
        run_container
        ;;
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    status)
        check_status
        ;;
    logs)
        view_logs
        ;;
    shell)
        get_shell
        ;;
    push)
        push_image
        ;;
    pull)
        pull_image
        ;;
    clean)
        clean_up
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        ;;
esac

exit 0

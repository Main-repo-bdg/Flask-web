# Docker Setup for Flask Webhook Viewer

This document explains how to use Docker with the Flask Webhook Viewer application.

## Prerequisites

- Docker installed on your machine ([Install Docker](https://docs.docker.com/get-docker/))
- Docker Compose installed (comes with Docker Desktop for Windows/Mac, [Install Docker Compose](https://docs.docker.com/compose/install/) for Linux)
- Docker Hub account (optional, only if you want to push your images)

## Quick Start

### Using docker_run.sh (recommended)

The easiest way to work with the Docker setup is using the provided `docker_run.sh` script:

```bash
# Make the script executable
chmod +x docker_run.sh

# Build the Docker image
./docker_run.sh build

# Run the container
./docker_run.sh run

# Check status
./docker_run.sh status

# View logs
./docker_run.sh logs

# Stop the container
./docker_run.sh stop
```

### Using Docker Compose

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs

# Stop the container
docker-compose down
```

### Using Docker directly

```bash
# Build the Docker image
docker build -t bdgtest/flask-webhook-viewer .

# Run the container
docker run -d --name flask-webhook-viewer -p 8000:8000 -v $(pwd)/data:/app/data bdgtest/flask-webhook-viewer

# Stop the container
docker stop flask-webhook-viewer
```

## Accessing the Application

Once the container is running, you can access the application at:

```
http://localhost:8000
```

## Environment Variables

You can configure the application using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| FLASK_ENV | Flask environment | production |
| DROPBOX_APP_KEY | Dropbox application key | - |
| DROPBOX_APP_SECRET | Dropbox application secret | - |
| DROPBOX_REFRESH_TOKEN | Dropbox refresh token | - |
| ENABLE_AUTO_BACKUP | Enable auto backup to Dropbox | False |
| DROPBOX_BACKUP_FOLDER | Dropbox backup folder path | /WebhookBackup |

### Setting Environment Variables

You can set environment variables in several ways:

1. In the `.env` file (mounted as a volume)
2. In the `docker-compose.yml` file under the `environment` section
3. When running with Docker directly using the `-e` flag:
   ```bash
   docker run -e FLASK_ENV=development -e ENABLE_AUTO_BACKUP=True ... bdgtest/flask-webhook-viewer
   ```

## Persistent Data

The application stores data in the `/app/data` directory inside the container. This is mounted as a volume to `./data` on your host system to ensure data persists across container restarts.

## Advanced Usage

### Custom Port

To use a different port on the host:

```bash
# Using docker_run.sh
PORT=9000 ./docker_run.sh run

# Using Docker Compose (edit docker-compose.yml first)
# Change "8000:8000" to "9000:8000"

# Using Docker directly
docker run -p 9000:8000 ... bdgtest/flask-webhook-viewer
```

### Custom Image Name

```bash
# Using docker_run.sh
IMAGE_NAME=myname/myapp ./docker_run.sh build
IMAGE_NAME=myname/myapp ./docker_run.sh run
```

### Getting a Shell Inside the Container

```bash
# Using docker_run.sh
./docker_run.sh shell

# Using Docker directly
docker exec -it flask-webhook-viewer /bin/bash
```

## Docker Hub Integration

The Docker setup is pre-configured to work with Docker Hub using the username `bdgtest`. 

### Logging in to Docker Hub

```bash
docker login -u bdgtest
# Enter your personal access token when prompted
```

### Pushing to Docker Hub

After building the image locally:

```bash
# Using docker_run.sh
./docker_run.sh push

# Using Docker directly
docker push bdgtest/flask-webhook-viewer
```

### Pulling from Docker Hub

```bash
# Using docker_run.sh
./docker_run.sh pull

# Using Docker directly
docker pull bdgtest/flask-webhook-viewer
```

## Docker Run Script Commands

The `docker_run.sh` script supports the following commands:

| Command | Description |
|---------|-------------|
| build | Build the Docker image |
| run | Run the Docker container |
| start | Start an existing container |
| stop | Stop the running container |
| restart | Restart the container |
| status | Show container status |
| logs | Show container logs |
| shell | Get a shell inside the container |
| push | Push image to Docker Hub |
| pull | Pull image from Docker Hub |
| clean | Remove container and image |
| help | Show help message |

## Troubleshooting

### Permission Issues

If you encounter permission issues with the data directory:

```bash
# Fix permissions for the data directory
chmod -R 777 ./data
```

### Container Won't Start

Check logs for errors:

```bash
./docker_run.sh logs
# or 
docker logs flask-webhook-viewer
```

### Can't Connect to the Application

Make sure the container is running and the port is correctly mapped:

```bash
./docker_run.sh status
# or
docker ps
```

Verify that no other application is using port 8000 on your host.

### Dropbox Integration Issues

If Dropbox integration isn't working, check that:

1. All required environment variables are set (see Environment Variables section)
2. The `.env` file is correctly mounted to the container
3. The Dropbox tokens are valid and have the correct permissions

## Cleaning Up

To remove all Docker resources related to the application:

```bash
./docker_run.sh clean
# or
docker-compose down --rmi all
```

#!/bin/bash
set -exuo pipefail

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install ca-certificates curl gnupg lsb-release -y
sudo mkdir -p /etc/apt/keyrings

echo "Installing Docker & Docker Compose"
ARCH=`dpkg --print-architecture`
RELEASE=`lsb_release -cs`
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $RELEASE stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker

echo "Starting test task"
BASEDIR=$(realpath $(dirname $0))
ROOT=$(realpath $BASEDIR/../)

cd $ROOT

# docker snapshot publication
echo "Building the image"
make docker-build

VAULT_ADDR=${VAULT_ADDR:-=https://vault-ci-prod.elastic.dev}
VAULT_USER="docker-swiftypeadmin"
echo "Fetching Docker credentials for '$VAULT_USER' from Vault..."
DOCKER_USER=$(vault read -address "${VAULT_ADDR}" -field login secret/ci/elastic-ent-search-ci-images/${VAULT_USER})
DOCKER_PASSWORD=$(vault read -address "${VAULT_ADDR}" -field password secret/ci/elastic-ent-search-ci-images/${VAULT_USER})
echo "Done!"
echo

echo "Logging into Docker as '$DOCKER_USER'..."
docker login -u "${DOCKER_USER}" -p ${DOCKER_PASSWORD} docker.elastic.co
echo "Done!"
echo
echo "Pushing the image to docker.elastic.co"
make docker-push

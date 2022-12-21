#!/bin/bash
set -euo pipefail

sudo apt-get update
sudo apt-get install ca-certificates curl gnupg lsb-release -y
sudo mkdir -p /etc/apt/keyrings

echo "Installing Docker & Docker Compose"
ARCH=`dpkg --print-architecture`
RELEASE=`lsb_release -cs`
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $RELEASE stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker

# installs Python 3.10
echo "Installing Python 3.10"
sudo apt upgrade -y --no-install-recommends
sudo apt-get remove python3-pip python3-setuptools -y
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa
sudo TZ=UTC apt install --no-install-recommends python3.10 python3.10-dev -y
curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.10


BASEDIR=$(realpath $(dirname $0))
ROOT=$(realpath $BASEDIR/../)

cd $ROOT/connectors/sources/tests/fixtures/mysql

export DATA_SIZE=small

make run-stack
sleep 120

make load-data

cd $ROOT
docker run --rm -v $ROOT:/ci -w=/ci \
    -it \
    python:3.10 \
    /bin/bash -c  "/ci/.buildkite/nightly.sh"

cd $ROOT/connectors/sources/tests/fixtures/mysql
make stop-stack

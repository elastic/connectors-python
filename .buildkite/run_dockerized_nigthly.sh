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

# installs Python 3.10
echo "Installing Python 3.10"
sudo apt-get remove python3-pip python3-setuptools -y
sudo DEBIAN_FRONTEND=noninteractive apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo TZ=UTC DEBIAN_FRONTEND=noninteractive apt install --no-install-recommends python3.10 python3.10-dev python3.10-venv -y


curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.10


echo "Starting test task"
BASEDIR=$(realpath $(dirname $0))
ROOT=$(realpath $BASEDIR/../)

cd $ROOT

/usr/bin/python3.10 -m venv .
export PERF8=$ROOT/bin/perf8
export PYTHON=$ROOT/bin/python
export PIP=$ROOT/bin/pip
export DATA_SIZE=small

$PIP install -r requirements/tests.txt
$PIP install -r requirements/x86_64.txt
cd $ROOT/connectors/sources/tests/fixtures/mysql
make run-stack
sleep 120

make load-data

cd $ROOT
$PYHON setup.py develop


make ftest NAME=mysql

cd $ROOT/connectors/sources/tests/fixtures/mysql
make stop-stack

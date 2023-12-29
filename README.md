# Tiny Chat

## :fire: Hint
This project is still in development, and welcome to join us if you are interested in IM

## Initialize Python Environment

1.Clone this repository and change the directory

```Shell
git clone https://github.com/garvenlee/tiny-chat-microservices.git
cd tiny-chat-microservices
```

2.Create one new Python environment

```Shell
conda create -n py311 python=3.11 -y
conda activate py311
```

<b>Note</b>: the whole development is only tested in Python3.11

3.Initialize the project

```Shell
cd chat
poetry init
cd common
python setup.py install
```

## Install external dependencies
You can use docker, Linux APT or whatever you can to deploy these dependencies

1.Redis

2.RabbitMQ (select the version which supports stream protocol)

3.ETCD

4.PostgresSQL

5.Cassandra

## Project Architecture Design
TODO 
#!/usr/bin/env python

import configparser
import json
import logging
import MySQLdb
import sys
import web3

from web3.middleware import geth_poa_middleware


class EthereumContractDeploy():
    def __init__(self, rpc, abi, bytecode, owner, password):
        self.w3_init(rpc)
        self.abi = abi
        self.bytecode = bytecode
        self.owner = owner
        self.password = password

    def w3_init(self, rpc):
        self.w3 = web3.Web3(web3.providers.rpc.HTTPProvider(rpc))
        self.w3.middleware_stack.inject(geth_poa_middleware, layer=0)

    def unlock_account(self):
        self.w3.personal.unlockAccount(self.owner, self.password)

    def deploy_contract(self, params):
        logging.info("Deploy contract with parameters" + str(params))
        logging.info("Unlock account")
        self.unlock_account()
        contract = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        txid = contract.constructor(*params).transact({"from": self.owner})
        logging.info("Transaction hash: " + txid.hex())
        tx_receipt = self.w3.eth.waitForTransactionReceipt(txid)
        return (tx_receipt["contractAddress"])


class MySQLQueue():
    def __init__(self, host, port, user, passwd, db, fields, convertFields):
        self.host = host
        self.port = port
        self.user = user
        self.passwd = passwd
        self.db = db
        self.fields = fields
        self.convertFields = convertFields
        self.connect_db()
        self.fetch_queue()
        self.convert_params()

    def connect_db(self):
        self.db = MySQLdb.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            passwd=self.passwd,
            db=self.db
        )

    def fetch_queue(self):
        c = self.db.cursor()
        sql = "SELECT id, {fields} FROM contracts WHERE status = 0;".format(
            fields=self.fields
        )
        c.execute(sql)
        self.queue = {}
        for row in c.fetchall():
            cid = row[0]
            params = list(row[1:])
            self.queue[cid] = params

    def get_queue(self):
        return self.queue

    def convert_params(self):
        addr = list(map(int, self.convertFields.split(",")))
        for params in self.queue.values():
            for i in addr:
                params[i] = web3.Web3.toChecksumAddress(params[i])

    def get_params(self, cid):
        return self.queue[cid]

    def save_result(self, cid, status, message, contract_address):
        c = self.db.cursor()
        sql = "UPDATE `contracts` SET `status`=%s, " + \
            "`contract_address`=%s, `message`=%s " + \
            "WHERE `id`=%s"
        data = (status, contract_address, message, cid)
        c.execute(sql, data)
        self.db.commit()


def batch_deploy(deploy, queue):
    for cid, params in queue.get_queue().items():
        try:
            address = deploy.deploy_contract(params)
            msg = "OK"
            status = 1
        except Exception as e:
            msg = str(e)
            status = -1
            address = ""
        queue.save_result(cid, status, msg, address)


def main():
    try:
        config_path = sys.argv[1]
    except IndexError:
        print("Usage: deploy.py <config_path>")

    config = configparser.ConfigParser()
    config.read(config_path)

    rpc = config["ethereum"]["rpc"]
    owner = web3.Web3.toChecksumAddress(config["ethereum"]["owner"])
    password = config["ethereum"]["unlockPassword"]
    abiPath = config["contract"]["abiPath"]
    bytecodePath = config["contract"]["bytecodePath"]
    host = config["mysql"]["host"]
    port = int(config["mysql"]["port"])
    user = config["mysql"]["user"]
    passwd = config["mysql"]["passwd"]
    db = config["mysql"]["db"]
    fields = config["mysql"]["fields"]
    convertFields = config["mysql"]["convertFields"]

    abi = json.loads(open(abiPath, "rt").read())
    bytecode = open(bytecodePath, "rt").read().strip()

    deploy = EthereumContractDeploy(rpc, abi, bytecode, owner, password)
    queue = MySQLQueue(host, port, user, passwd, db, fields, convertFields)

    batch_deploy(deploy, queue)


if __name__ == "__main__":
    logger = logging.getLogger('deploy ethereum')
    logger.setLevel(logging.DEBUG)
    main()

import torch
import os
import argparse
from collections import namedtuple
import numpy as np
import yaml
import pickle

from registry import Model, Strategy
from environments.var_voltage_control.voltage_control_env import VoltageControl
from utilities.util import convert
from utilities.tester import PGTester
from tensorboardX import SummaryWriter


parser = argparse.ArgumentParser(description="Train rl agent.")
parser.add_argument("--save-path", type=str, nargs="?", default="./", help="Please enter the directory of saving model.")
parser.add_argument("--alg", type=str, nargs="?", default="maddpg", help="Please enter the alg name.")
parser.add_argument("--env", type=str, nargs="?", default="var_voltage_control", help="Please enter the env name.")
parser.add_argument("--alias", type=str, nargs="?", default="", help="Please enter the alias for exp control.")
parser.add_argument("--difficulty", type=str, nargs="?", default="easy", help="Please enter the difficulty level: easy or hard.")
parser.add_argument("--mode", type=str, nargs="?", default="distributed", help="Please enter the mode: distributed or decentralised.")
parser.add_argument("--scenario", type=str, nargs="?", default="bus33bw", help="Please input the valid name of an environment scenario.")
parser.add_argument("--reward-type", type=str, nargs="?", default="l1", help="Please input the valid reward type: l1, liu, l2 or bowl.")
parser.add_argument("--test-mode", type=str, nargs="?", default="single", help="Please input the valid test mode: single or batch.")
argv = parser.parse_args()

# load env args
with open("./args/env_args/"+argv.env+".yaml", "r") as f:
    env_config_dict = yaml.safe_load(f)["env_args"]
data_path = env_config_dict["data_path"].split("/")
data_path[-1] = argv.scenario
env_config_dict["data_path"] = "/".join(data_path)
net_topology = argv.scenario
assert net_topology in ['bus33bw_gu', 'bus141_gu', 'bus347_gu'], f'{net_topology} is not a valid scenario.'
if argv.difficulty == "easy":
    env_config_dict["pv_scale"] = 0.5
    env_config_dict["demand_scale"] = 1.0
    if argv.scenario == 'bus33bw_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.7
    elif argv.scenario == 'bus141_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.8
    elif argv.scenario == 'bus347':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.5
elif argv.difficulty == "hard":
    env_config_dict["pv_scale"] = 0.8
    env_config_dict["demand_scale"] = 1.0
    if argv.scenario == 'bus33bw_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.7
    elif argv.scenario == 'bus141_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.8
    elif argv.scenario == 'bus347_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.4
elif argv.difficulty == "super_hard":
    env_config_dict["pv_scale"] = 1.0
    env_config_dict["demand_scale"] = 1.0
    if argv.scenario == 'bus33bw_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.5
    elif argv.scenario == 'bus141_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.6
    elif argv.scenario == 'bus347_gu':
        env_config_dict["action_bias"] = 0.0
        env_config_dict["action_scale"] = 0.3
else:
    raise RuntimeError("Please input the correct difficulty level, e.g. easy, hard or super_hard.")
assert argv.mode in ['distributed', 'decentralised'], "Please input the correct mode, e.g. distributed or decentralised."
env_config_dict["mode"] = argv.mode

env_config_dict["reward_type"] = argv.reward_type

# load default args
with open("./args/default.yaml", "r") as f:
    default_config_dict = yaml.safe_load(f)

# load alg args
with open("./args/alg_args/"+argv.alg+".yaml", "r") as f:
    alg_config_dict = yaml.safe_load(f)["alg_args"]
    alg_config_dict["action_scale"] = env_config_dict["action_scale"]
    alg_config_dict["action_bias"] = env_config_dict["action_bias"]

log_name = "-".join([argv.env, net_topology, argv.difficulty, argv.mode, argv.alg, argv.reward_type, argv.alias])
alg_config_dict = {**default_config_dict, **alg_config_dict}

# define envs
env = VoltageControl(env_config_dict)

alg_config_dict["agent_num"] = env.get_num_of_agents()
alg_config_dict["obs_size"] = env.get_obs_size()
alg_config_dict["action_dim"] = env.get_total_actions()
alg_config_dict["cuda"] = False
args = convert(alg_config_dict)

# define the save path
if argv.save_path[-1] is "/":
    save_path = argv.save_path
else:
    save_path = argv.save_path+"/"

LOAD_PATH = save_path+log_name+"/model.pt"

model = Model[argv.alg]

strategy = Strategy[argv.alg]

if args.target:
    target_net = model(args)
    behaviour_net = model(args, target_net)
else:
    behaviour_net = model(args)
checkpoint = torch.load(LOAD_PATH, map_location='cpu') if not args.cuda else torch.load(LOAD_PATH)
behaviour_net.load_state_dict(checkpoint['model_state_dict'])

print (f"{args}\n")

if strategy == "pg":
    test = PGTester(args, behaviour_net, env)
elif strategy == "q":
    raise NotImplementedError("This needs to be implemented.")
else:
    raise RuntimeError("Please input the correct strategy, e.g. pg or q.")

if argv.test_mode == 'single':
    # record = test.run(199, 23, 2) # (day, hour, quarter)
    record = test.run(730, 23, 2) # (day, hour, quarter)
elif argv.test_mode == 'batch':
    record = test.batch_run(10)

with open('test_record_'+log_name+'_'+argv.test_mode+'.pickle', 'wb') as f:
    pickle.dump(record, f, pickle.HIGHEST_PROTOCOL)

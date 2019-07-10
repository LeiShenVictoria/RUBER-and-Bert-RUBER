#!/usr/bin/python3
# Author: GMFTBY
# Time: 2019.7.10

'''
utils file contains the tool function
1. bert embedding collect (query, groundtruth, generated)
2. load_best_model
3. batch iterator
'''

import pickle
import torch
import numpy as np
import os
from bert_serving.client import BertClient
bc = BertClient()


def load_best_model(net):
    path = f"./ckpt/"
    best_acc, best_file = -1, None
    best_epoch = -1
    
    for file in os.listdir(path):
        try:
            _, acc, _, loss, _, epoch = file.split("_")
            epoch = epoch.split('.')[0]
        except:
            continue
        acc = float(acc)
        epoch = int(epoch)
        # if epoch > best_epoch:
        if acc > best_acc:
            best_file = file
            # best_epoch = epoch
            best_acc = acc

    if best_file:
        file_path = path + best_file
        print(f'[!] Load the model from {file_path}')
        net.load_state_dict(torch.load(file_path)['net'])
    else:
        raise Exception(f"[!] No saved model")


def get_batch(qpath, rpath, batch_size):
    # bert embedding matrix, [dataset_size, 768]
    # return batch shape: [B, 768]
    with open(qpath, 'rb') as f:
        qdataset = pickle.load(f)
        
    with open(rpath, 'rb') as f:
        rdataset = pickle.load(f)
        
    size = len(qdataset)
    idx = 0
    while True:
        qbatch = qdataset[idx:idx+batch_size]
        rbatch = rdataset[idx:idx+batch_size]
        pidx = np.random.choice(rdataset.shape[0], batch_size)
        nbatch = rdataset[pidx]
        
        qbatch = np.concatenate([qbatch, qbatch])
        rbatch = np.concatenate([rbatch, nbatch])
        
        label = np.concatenate([np.ones(int(qbatch.shape[0] / 2)),
                                np.zeros(int(qbatch.shape[0] / 2))])
        
        # shuffle
        pureidx = np.arange(qbatch.shape[0])
        np.random.shuffle(pureidx)
        qbatch = qbatch[pureidx]
        rbatch = rbatch[pureidx]
        label = label[pureidx]
        
        idx += batch_size
        yield qbatch, rbatch, label
        
        if idx > size:
            break
    return None
    

def process_train_file(path, embed_path, batch_size=128):
    # batch_size: batch for bert to feedforward
    dataset = []
    with open(path) as f:
        for line in f.readlines():
            dataset.append(''.join(line.strip().split()))
    
    # bert-as-serive
    embed = []
    idx = 0
    while True:
        batch = dataset[idx:idx+batch_size]
        rest = bc.encode(batch)    # [batch_size, 768]
        embed.append(rest)
        idx += batch_size
        if idx > len(dataset):
            break
        print(f'{idx} / {len(dataset)}', end='\r')
    embed = np.concatenate(embed)  # [dataset_size, 768]
    
    with open(embed_path, 'wb') as f:
        pickle.dump(embed, f)
        
    print(f'Write the bert embedding into {embed_path}')
        
            

if __name__ == "__main__":
    process_train_file('./data/src-train.txt', './data/src-train.embed')
    process_train_file('./data/tgt-train.txt', './data/tgt-train.embed')
    process_train_file('./data/src-dev.txt', './data/src-dev.embed')
    process_train_file('./data/tgt-dev.txt', './data/tgt-dev.embed')
    process_train_file('./data/src-test.txt', './data/src-test.embed')
    process_train_file('./data/tgt-test.txt', './data/tgt-test.embed')
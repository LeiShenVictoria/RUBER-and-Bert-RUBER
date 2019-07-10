#!/usr/bin/python
# Author: GMFTBY
# Time: 2019.7.10


import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.nn.utils import clip_grad_norm_
import numpy as np

import argparse
import os
import sys
import time
import pprint
import csv
import math
from tqdm import tqdm
import ipdb
import scipy
from scipy.stats.mstats import gmean
from scipy.stats import pearsonr, spearmanr
from nltk.translate import bleu
from nltk.translate.bleu_score import SmoothingFunction
from nltk.translate.bleu_score import sentence_bleu

from reference_score import *
from unreference_score import *
from utils import *

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

def collection_result(contextp, groundp, predp):
    # context, groundtruth, generate
    context, groundtruth, reply = [], [], []
    with open(contextp) as f:
        for line in f.readlines():
            context.append(line.strip())
    with open(groundp) as f:
        for line in f.readlines():
            groundtruth.append(line.strip())
    with open(predp) as f:
        for line in f.readlines():
            reply.append(line.strip())
    return context, groundtruth, reply


def cal_BLEU(refer, candidate, ngram=1):
    smoothie = SmoothingFunction().method4
    if ngram == 1:
        weight = (1, 0, 0, 0)
    elif ngram == 2:
        weight = (0.5, 0.5, 0, 0)
    elif ngram == 3:
        weight = (0.33, 0.33, 0.33, 0)
    elif ngram == 4:
        weight = (0.25, 0.25, 0.25, 0.25)
    return sentence_bleu(refer, candidate, weights=weight, smoothing_function=smoothie)


def show(scores, model_scores, mode):
    print(f'========== Method {mode} result ==========')
    p, pp = pearsonr(scores, model_scores)
    p, pp = round(p, 5), round(pp, 5)
    s, ss = spearmanr(scores, model_scores)
    s, ss = round(s, 5), round(ss, 5)
    print('Pearson(p-value):', f'{p}({pp})')
    print('Spearman(p-value):', f'{s}({ss})')
    print(f'========== Method {mode} result ==========')
    
    
def read_human_score(path1, path2):
    def read_file(path):
        with open(path) as f:
            score = []
            for line in f.readlines():
                score.append(float(line.strip()))
        return score
    score1 = read_file(path1)
    score2 = read_file(path2)
    return score1, score2


class BERT_RUBER:
    
    def __init__(self):
        self.refer = BERT_RUBER_refer()
        self.unrefer = BERT_RUBER_unrefer(768)
        
        load_best_model(self.unrefer)
        
        if torch.cuda.is_available():
            self.unrefer.cuda()
            self.unrefer.eval()
            
    def normalize(self, scores):
        smin = min(scores)
        smax = max(scores)
        diff = smax - smin
        ret = [(s - smin) / diff for s in scores]
        return ret
    
    def score(self, query, groundtruth, reply, method='Min'):
        q = self.refer.encode_sentence(query)
        r = self.refer.encode_sentence(reply)
        g = self.refer.encode_sentence(groundtruth)
        q, r, g = torch.from_numpy(q), torch.from_numpy(r), torch.from_numpy(g)
        q = q.unsqueeze(0)
        r = r.unsqueeze(0)
        g = g.unsqueeze(0)
        
        if torch.cuda.is_available():
            q, r, g = q.cuda(), r.cuda(), g.cuda()
        
        unrefer_score = self.unrefer(q, r)
        unrefer_score = unrefer_score[0].item()
        refer_score = self.refer.cos_similarity(groundtruth, reply)
        
        return unrefer_score, refer_score
    
    def scores(self, contexts, gs, rs, method='Min'):
        refer, unrefer = [], []
        pbar = tqdm(zip(contexts, gs, rs))
        for c, g, r in pbar:
            c = ''.join(c.split())
            g = ''.join(g.split())
            r = ''.join(r.split())
            if not r:
                # no words genereated
                r = '<unk>'
            if not c:
                c = '<unk>'
            unrefer_score, refer_score = self.score(c, g, r, method=method)
            refer.append(refer_score)
            unrefer.append(unrefer_score)
            pbar.set_description('')
        refer = self.normalize(refer)
        unrefer = self.normalize(unrefer)
        ruber = self.hybird_score(refer, unrefer)
        
        return refer, unrefer, ruber
    
    def hybird_score(self, refer, unrefer, method='Min'):
        # make sure refer and unrefer has been normed
        if method == 'Min':
            return [min(a,b) for a,b in zip(refer, unrefer)]
        elif method == 'Max':
            return [max(a,b) for a,b in zip(refer, unrefer)]
        else:
            raise Exception("Can not find the right method")


if __name__ == "__main__":
    model = BERT_RUBER()
    context, groundtruth, reply = collection_result('./data/sample-300.txt',
                                                    './data/sample-300-tgt.txt',
                                                    './data/pred.txt')
    print(f'[!] read file')
    bleu1_scores, bleu2_scores, bleu3_scores, bleu4_scores = [], [], [], []
    
    # BERT RUBER
    refers, unrefer, ruber = model.scores(context, groundtruth, reply, method='Min')
    # BLEU
    for c, g, r in zip(context, groundtruth, reply):
        refer, condidate = g.split(), r.split()
        bleu1_scores.append(cal_BLEU(refer, condidate, ngram=1))
        bleu2_scores.append(cal_BLEU(refer, condidate, ngram=2))
        bleu3_scores.append(cal_BLEU(refer, condidate, ngram=3))
        bleu4_scores.append(cal_BLEU(refer, condidate, ngram=4))
    print(f'[!] compute the score')
    
    # human scores
    h1, h2 = read_human_score('./data/lantian1-xiaohuangji-rest.txt',
                              './data/lantian2-xiaohuangji-rest.txt')
    print(f'[!] read human score')
    
    show(h1, h2, 'Human')
    show(h1, bleu1_scores, "BLEU-1")
    show(h1, bleu2_scores, "BLEU-2")
    show(h1, bleu3_scores, "BLEU-3")
    show(h1, bleu4_scores, "BLEU-4")
    show(h1, unrefer, "BERT s_U")
    show(h1, refers, "BERT s_R")
    show(h1, ruber, "BERT RUBER")

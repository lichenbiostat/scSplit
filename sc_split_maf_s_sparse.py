"""
Reference free MAF-based demultiplexing on pooled scRNA-seq
Jon Xu (jun.xu@uq.edu.au)
Lachlan Coin
Aug 2018
"""

import sys
import math
import numpy as np
import pandas as pd
from scipy.stats import binom
from scipy.sparse import csr_matrix
import datetime
import csv

class models:
    def __init__(self, base_calls_mtx, num=2):
        """
        A complete model class containing SNVs, matrices counts, barcodes, model minor allele frequency with assigned cells 

        Parameters:
             base_calls_mtx(list of Dataframes): SNV-barcode matrix containing lists of base calls
             all_POS(list): list of SNVs positions
             barcodes(list): list of cell barcodes
             num(int): number of total samples
             P_s_c(DataFrame): barcode/sample matrix containing the probability of seeing sample s with observation of barcode c
             lP_c_s(DataFrame): barcode/sample matrix containing the log likelihood of seeing barcode c under sample s, whose sum should increase by each iteration
             assigned(list): final lists of cell/barcode assigned to each cluster/model
             model_MAF(list): list of num model minor allele frequencies based on P(A)

        """

        self.ref_bc_mtx = base_calls_mtx[0]
        self.alt_bc_mtx = base_calls_mtx[1]
        self.all_POS = base_calls_mtx[2].tolist()
        self.barcodes = base_calls_mtx[3].tolist()
        self.num = num
        self.P_s_c = pd.DataFrame(np.zeros((len(self.barcodes), self.num)), index = self.barcodes, columns = list(range(self.num)))
        self.lP_c_s = pd.DataFrame(np.zeros((len(self.barcodes), self.num)), index = self.barcodes, columns = list(range(self.num)))
        self.assigned = []
        self.model_MAF = pd.DataFrame(np.zeros((len(self.all_POS), self.num)), index=self.all_POS, columns=range(self.num))
        for _ in range(self.num):
            self.assigned.append([])

        for n in range(self.num):
            # use total ref count and alt count to generate probability simulation
            beta_sim = np.random.beta(self.ref_bc_mtx.sum(), self.alt_bc_mtx.sum(), size = (len(self.all_POS), 1))
            self.model_MAF.loc[:, n] = [1 - item[0] for item in beta_sim]   # P(A) = 1 - P(R)


    def calculate_model_MAF(self):
        """
        Update the model minor allele frequency by distributing the alt and total counts of each barcode on a certain snv to the model based on P(s|c)

        """

        self.model_MAF = pd.DataFrame((self.alt_bc_mtx.dot(self.P_s_c) + 1) / ((self.alt_bc_mtx + self.ref_bc_mtx).dot(self.P_s_c) + 2))


    def calculate_cell_likelihood(self):
        """
        Calculate cell|sample likelihood P(c|s) and derive sample|cell probability P(s|c)
        P(c|s_v) = P(N(A),N(R)|s) = P(A|s)^N(A) * (1-P(A|s))^N(R)
        log(P(c|s)) = sum_v{(N(A)_c,v*log(P(A|s)) + N(R)_c,v*log(1-P(A|s)))}
        P(s_n|c) = P(c|s_n) / [P(c|s_1) + P(c|s_2) + ... + P(c|s_n)]

        """

        for n in range(self.num):
            matcalc = self.alt_bc_mtx.T.multiply(self.model_MAF.loc[:, n].apply(np.log2)).T \
                    + self.ref_bc_mtx.T.multiply((1 - self.model_MAF.loc[:, n]).apply(np.log2)).T
            self.lP_c_s.loc[:, n] = matcalc.sum(axis=0).tolist()[0]  # log likelihood to avoid python computation limit of 2^+/-308

        # log(P(s1|c) = log{1/[1+P(c|s2)/P(c|s1)]} = -log[1+P(c|s2)/P(c|s1)] = -log[1+2^(logP(c|s2)-logP(c|s1))]
        for i in range(self.num):
            denom = 0
            for j in range(self.num):
                denom += 2 ** (self.lP_c_s.loc[:, j] - self.lP_c_s.loc[:, i])
            self.P_s_c.loc[:, i] = 1 / denom


    def assign_cells(self):
        """
	    Final assignment of cells according to P(s|c) >= 0.9

	    """

        for n in range(self.num):
            self.assigned[n] = sorted(self.P_s_c.loc[self.P_s_c[n] >= 0.9].index.values.tolist())


def run_model(base_calls_mtx, num_models):

    model = models(base_calls_mtx, num_models)
    
    iterations = 0
    sum_log_likelihood = []

    # commencing E-M
    while iterations < 15:

        iterations += 1
        print("Iteration {}".format(iterations))
        model.calculate_cell_likelihood()
        print("Cell origin probabilities ", model.P_s_c)
        model.calculate_model_MAF()
        print("Model MAF: ", model.model_MAF)
        sum_log_likelihood.append(model.lP_c_s.sum().sum())

    model.assign_cells()

    # generate outputs
    for n in range(num_models):
        with open('barcodes_maf_s_sparse_{}.csv'.format(n), 'w') as myfile:
            for item in model.assigned[n]:
                myfile.write(str(item) + '\n')
    model.P_s_c.to_csv('P_s_c_maf_s_sparse.csv')
    print(sum_log_likelihood)
    print("Finished model at {}".format(datetime.datetime.now().time()))


def read_base_calls_matrix(ref_csv, alt_csv):

    """ Read in existing matrix from the csv files """

    ref = pd.read_csv(ref_csv, header=0, index_col=0)
    alt = pd.read_csv(alt_csv, header=0, index_col=0)
    ref_s = csr_matrix(ref.values)
    alt_s = csr_matrix(alt.values)
    base_calls_mtx = [ref_s, alt_s, ref.index, ref.columns]
    print("Base call matrix finished", datetime.datetime.now().time())
    return base_calls_mtx


def main():

    num_models = 2          # number of models in each run

    # Mixed donor files
    ref_csv = 'ref_filtered.csv'  # reference matrix
    alt_csv = 'alt_filtered.csv'  # alternative matrix

    print ("Starting data collection", datetime.datetime.now().time())
    
    base_calls_mtx = read_base_calls_matrix(ref_csv, alt_csv)

    run_model(base_calls_mtx, num_models)

if __name__ == "__main__":
    main()


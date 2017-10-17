#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 29 09:20:28 2017

@author: ajaver
"""
import pandas as pd
import tables
import numpy as np
import random
import time
import warnings

wild_isolates = ['JU393', 'ED3054', 'JU394', 
                 'N2', 'JU440', 'ED3021', 'ED3017', 
                 'JU438', 'JU298', 'JU345', 'RC301', 
                 'AQ2947', 'ED3049',
                 'LSJ1', 'JU258', 'MY16', 
                 'CB4852', 'CB4856', 'CB4853',
                 ]

def _h_angles(skeletons):
    dd = np.diff(skeletons,axis=1);
    angles = np.arctan2(dd[...,0], dd[...,1])
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        angles = np.unwrap(angles, axis=1);
    
    mean_angles = np.mean(angles, axis=1)
    angles -= mean_angles[:, None]
    
    return angles, mean_angles



    #%%

class SkeletonsFlow():
    def __init__(self,
                n_batch,
                main_file,
                set_type = None,
                min_num_samples = 1,
                valid_strains = None,
                expected_fps = 30,
                sample_size_frames_s = 90,
                sample_frequency_s = 1/10,
                body_range = (8, 41),
                is_angle = False
                ):
        
        self.n_batch = n_batch
        self.sample_size_frames = sample_size_frames_s*expected_fps
        self.sample_frequency  = sample_frequency_s*expected_fps
        self.main_file = main_file
        self.body_range = body_range
        self.is_angle = is_angle
        
        with pd.HDFStore(self.main_file, 'r') as fid:
            df1 = fid['/skeletons_groups']
            df2 = fid['/strains_codes']
        
        #number of classes for the one-hot encoding
        self.n_clases = df2['strain_id'].max() + 1
        
        skeletons_indexes = pd.merge(df1, df2, on='strain')
        good = skeletons_indexes.apply(lambda x : x['fin'] - x['ini'] >= self.sample_size_frames, axis=1)
        skeletons_indexes = skeletons_indexes[good]
        
        if set_type is not None:
            assert set_type in ['train', 'test', 'val', 'tiny']
            with tables.File(self.main_file, 'r') as fid:
                #use previously calculated indexes to divide data in training, validation and test sets
                valid_indices = fid.get_node('/index_groups/' + set_type)[:]
                skeletons_indexes = skeletons_indexes.loc[valid_indices]
        

        skeletons_indexes = skeletons_indexes.groupby('strain_id').filter(lambda x: len(x['experiment_id'].unique()) >= min_num_samples)
        if valid_strains is not None:
            skeletons_indexes = skeletons_indexes[skeletons_indexes['strain'].isin(valid_strains)]

        
        self.skeletons_indexes = skeletons_indexes
        self.skeletons_groups = skeletons_indexes.groupby('strain_id')
        self.strain_ids = list(map(int, self.skeletons_groups.indices.keys()))
        
    def _random_choice(self):
        strain_id, = random.sample(self.strain_ids, 1)
        gg = self.skeletons_groups.get_group(strain_id)
        ind, = random.sample(list(gg.index), 1)
        dat = gg.loc[ind]
        
        r_f = dat['fin'] - self.sample_size_frames
        ini_r = random.randint(dat['ini'], r_f)
        
        row_indices = np.arange(ini_r, ini_r + self.sample_size_frames, self.sample_frequency)
        row_indices = np.round(row_indices).astype(np.int32)
        
        while True:
            try:
                #read data
                with tables.File(self.main_file, 'r') as fid:
                    skeletons = fid.get_node('/skeletons_data')[row_indices, :, :]
                    break
            except KeyError: 
                print('There was an error reading the file, I will try again...')
                time.sleep(1)
        
        if np.any(np.isnan(skeletons)):
            print(strain_id, ind, row_indices)
            #if there are nan we have a bug... i am not sure how to solve it...
            import pdb
            pdb.set_trace()
        
        body_coords = np.mean(skeletons[:, self.body_range[0]:self.body_range[1]+1, :], axis=1)
        skeletons -= body_coords[:, None, :]
        
        return strain_id, skeletons
    
    def _random_transform(self, skeletons):
        #random rotation
        theta = random.uniform(-np.pi, np.pi)
        rot_matrix = np.array([[np.cos(theta), -np.sin(theta)], 
                             [np.sin(theta),  np.cos(theta)]])
        
        skel_r = skeletons.copy()
        for ii in range(skel_r.shape[1]):
            skel_r[:, ii, :] = np.dot(rot_matrix, skeletons[:, ii, :].T).T
        
        #random mirrowing 
        #for ii in range(skel_r.shape[-1]):
        #    skel_r[:, :, ii] *= random.choice([-1, 1])
         
        return skel_r
    
    def next_single(self):
         strain_id, skeletons = self._random_choice()

         if not self.is_angle:
            X = self._random_transform(skeletons)
         else:
            X, _ = _h_angles(skeletons)
            X = X[..., None]

         Y = np.zeros(self.n_clases, np.int32)
         Y[strain_id] = 1
         return X,Y
     
    def __next__(self):
        D = [self.next_single() for n in range(self.n_batch)]
        X, Y = map(np.array, zip(*D))
        return X,Y
    
    def __len__(self):
        return self.skeletons_indexes.shape[0]
    
if __name__ == '__main__':
    import matplotlib.pylab as plt
    import sys
    if sys.platform == 'linux':
        log_dir_root = '/work/ajaver/classify_strains/results'
        #main_file = '/work/ajaver/classify_strains/train_set/SWDB_skel_smoothed.hdf5'
    else:        
        log_dir_root = '/Users/ajaver/OneDrive - Imperial College London/classify_strains'
        #main_file = '/Users/ajaver/Desktop/SWDB_skel_smoothed.hdf5'
        main_file = '/Users/ajaver/Desktop/CeNDR_skel_smoothed.hdf5'

    if True:
        #valid_strains = ['AQ1033', 'AQ1037', 'AQ1038', 'CB1069', 'CB5', 'ED3054', 'JU438',
        #     'MT2248', 'MT8504', 'N2', 'NL1137', 'RB2005', 'RB557', 'VC12']
        
        #valid_strains = None
        valid_strains = ['N2']
        n_batch = 2
        sample_size_frames_s = 90
    
        train_generator = SkeletonsFlow(main_file = main_file, 
                                       n_batch = n_batch, 
                                       set_type='train',
                                       valid_strains = valid_strains
                                       )
        val_generator = SkeletonsFlow(main_file = main_file, 
                                       n_batch = n_batch, 
                                       set_type='val',
                                       valid_strains = valid_strains
                                       )
        test_generator = SkeletonsFlow(main_file = main_file, 
                                       n_batch = n_batch, 
                                       set_type='test',
                                       valid_strains = valid_strains
                                       )
        
        #%%
        with pd.HDFStore(train_generator.main_file, 'r') as fid:
            strains_codes = fid['/strains_codes']
        X,Y = next(train_generator)
        
        ss_ = strains_codes.loc[np.argmax(Y, axis=1)]['strain']
        #%%
        for x, ss in zip(X, ss_):
            plt.figure()
            plt.subplot(2,1,1)
            plt.imshow(x[:, :, 1].T, aspect='auto', interpolation='none')
            plt.subplot(2,1,2)
            plt.imshow(x[:, :, 0].T, aspect='auto', interpolation='none')
            
            plt.suptitle(ss)
            
            
            #%%
            angs, ang_ = _h_angles(x)
            plt.imshow(angs.T, aspect='auto', interpolation='none')
            #%%
            #dat = x[::25]
            #dd = np.arange(dat.shape[0])*1000
            #plt.figure()
            #plt.plot(dat[...,0].T+ dd, dat[...,1].T)
        #%%
        dd = train_generator.skeletons_indexes['fin'] - train_generator.skeletons_indexes['ini']
        
    
    #%%
    if False:
        sample_frequency_s = [1/30, 1/10, 1/3, 1, 3, 6]
        for sf in sample_frequency_s:
            print('*** {} ***'.format(sf))
            gen = SkeletonsFlow(main_file = main_file, 
                                   n_batch = 1, 
                                   set_type = 'val',
                                   valid_strains = wild_isolates,
                                   sample_frequency_s = sf
                                   )
            
            X,Y = next(gen)
            x = X[0]
            plt.figure()
            plt.subplot(2,1,1)
            plt.imshow(x[:, :, 1].T, aspect='auto', interpolation='none')
            plt.subplot(2,1,2)
            plt.imshow(x[:, :, 0].T, aspect='auto', interpolation='none')
            
            print(X.shape)
        
        for ts in [15, 30, 60, 90, 120, 300, 600, 840]:
            gen = SkeletonsFlow(main_file = main_file, 
                                   n_batch = 1, 
                                   set_type = 'val',
                                   valid_strains = wild_isolates,
                                   sample_size_frames_s = ts
                                   )
            
            print('*** {} ***'.format(ts))
            dd = gen.skeletons_indexes['strain'].value_counts()
            print(dd)
            print(set(wild_isolates)-set(dd.index))
        
#    #%%
#    gen = SkeletonsFlow(main_file = main_file, 
#                               n_batch = 1, 
#                               set_type = 'val',
#                               valid_strains = wild_isolates,
#                               sample_frequency_s = 1/30,
#                               sample_size_frames_s = 840
#                               )
#    X,Y = next(gen)
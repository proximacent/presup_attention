# Author: Andre Cianflone

# cmd to test a sample:
# python main.py --load_saved --ckpt_name also_word --mode 0
# debug
# python -m pudb main.py --load_saved --ckpt_name also_word --mode 0
from pdb import set_trace
import sys
import os
import tensorflow as tf
import numpy as np
from call_model import train_model, examine_attn, save_results
from utils import HParams, load_model, data_info, print_info
from CNN_sentence import load_data
# Control repeatability
random_seed=1
tf.set_random_seed(random_seed)

if __name__=="__main__":
  # Get hyperparams from argparse and defaults
  hp = HParams()
  mode = hp.mode

  # Get data
  emb, word_idx_map, data, postag_size = load_data(hp.data_dir, hp.pickle, tagged=hp.postags)
  print_info(data)

  # Inverse vocab
  inv_vocab =  data_info(emb,word_idx_map)

  # Start tf session
  with tf.Graph().as_default(), tf.Session() as sess:
    # Get the model
    model, saver, hp, result = load_model(sess, emb, hp, postag_size)

    # Check the params
    print(hp)

    # Train the model or examine results
    if mode == 1:
      # Train the model!
      train_model(hp, sess, saver, model, result, data)
    else:
      save_results(sess,data,model, hp)
      for i in range(50):
        name = 'viz/' + str(i) + '.png'
        # examine_attn(hp, sess, model, word_idx_map, inv_vocab, data, name)
    pass



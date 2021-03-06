#!/usr/bin/python
# -*- coding:utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals  # compatible with python3 unicode coding

import time
import numpy as np
import tensorflow as tf
import os
from sklearn.metrics import precision_recall_fscore_support
import nlp.seg.data_reader as reader  # absolute import
from nlp.seg.bilstm_model import SegTagger
from nlp.seg.data_Config import data_config
from nlp.seg.data_Config import LargeConfigChinese

dataConfig=data_config()

if not os.path.exists(dataConfig.train_dir):
    os.makedirs(dataConfig.train_dir)


def data_type():
    return tf.float32

# seg model configuration, set target num, and input vocab_size


def get_config():
    return LargeConfigChinese()



def run_epoch(session, model, word_data, tag_data, eval_op, verbose=False):
    """Runs the model on the given data."""
    epoch_size = ((len(word_data) // model.batch_size) - 1) // model.num_steps

    start_time = time.time()
    costs = 0.0
    iters = 0

    for step, (x, y) in enumerate(reader.iterator(word_data, tag_data, model.batch_size,
                                                  model.num_steps)):
        fetches = [model.cost, model.logits, eval_op]  # eval_op define the m.train_op or m.eval_op
        feed_dict = {}
        feed_dict[model.input_data] = x
        feed_dict[model.targets] = y
        cost, logits, _ = session.run(fetches, feed_dict)
        costs += cost
        iters += model.num_steps

        if verbose and step % (epoch_size // 10) == 10:
            print("%.3f perplexity: %.3f speed: %.0f wps" %
                  (step * 1.0 / epoch_size, np.exp(costs / iters),
                   iters * model.batch_size / (time.time() - start_time)))

        # Save Model to CheckPoint when is_training is True
        if model.is_training:
            if step % (epoch_size // 10) == 10:
                checkpoint_path = dataConfig.ckpt_path
                model.saver.save(session, checkpoint_path)
                print("Model Saved... at time step " + str(step))

    return np.exp(costs / iters)


def run_epoch_evaluate(session, model, word_data, tag_data, eval_op, verbose=False):
    """Runs the model on the given data."""
    epoch_size = ((len(word_data) // model.batch_size) - 1) // model.num_steps

    start_time = time.time()
    costs = 0.0
    iters = 0
    predict_id = []
    for step, (x, y) in enumerate(reader.iterator(word_data, tag_data, model.batch_size,
                                                  model.num_steps)):
        fetches = [model.cost, model.logits, eval_op]  # eval_op define the m.train_op or m.eval_op
        feed_dict = {}
        feed_dict[model.input_data] = x
        feed_dict[model.targets] = y
        cost, logits, _ = session.run(fetches, feed_dict)
        costs += cost
        iters += model.num_steps
        x, y = logits.shape
        if x > 1:
            for s in logits:
                predict_id.append(int(np.argmax(s)))
        else:
            predict_id.append(int(np.argmax(logits)))
    print("warn_for=('precision', 'recall', 'f-score'),")
    print(precision_recall_fscore_support(tag_data[:len(predict_id)], predict_id, average='weighted'))
    return np.exp(costs / iters)


def main(_):
    if not dataConfig.data_path:
        raise ValueError("No data files found in 'data_path' folder")

    raw_data = reader.load_data(dataConfig)
    train_word, train_tag, dev_word, dev_tag, test_word, test_tag, vocabulary = raw_data
    config = get_config()
    eval_config = get_config()
    eval_config.batch_size = 1
    eval_config.num_steps = 1

    with tf.Graph().as_default(), tf.Session() as session:
        initializer = tf.random_uniform_initializer(-config.init_scale,
                                                    config.init_scale)
        with tf.variable_scope("seg_var_scope", reuse=None, initializer=initializer):
            m = SegTagger(is_training=True, config=config)
        with tf.variable_scope("seg_var_scope", reuse=True, initializer=initializer):
            mvalid = SegTagger(is_training=False, config=config)
            mtest = SegTagger(is_training=False, config=config)

        # CheckPoint State
        ckpt = tf.train.get_checkpoint_state(dataConfig.data_path)
        if ckpt:
            print("Loading model parameters from %s" % ckpt.model_checkpoint_path)
            m.saver.restore(session, tf.train.latest_checkpoint(dataConfig.data_path))
        else:
            print("Created model with fresh parameters.")
            session.run(tf.global_variables_initializer())

        for i in range(config.max_max_epoch):
            lr_decay = config.lr_decay ** max(i - config.max_epoch, 0.0)
            m.assign_lr(session, config.learning_rate * lr_decay)
            print("Epoch: %d Learning rate: %.3f" % (i + 1, session.run(m.lr)))
            train_perplexity = run_epoch(session, m, train_word, train_tag, m.train_op,
                                         verbose=True)
            print("Epoch: %d Train Perplexity: %.3f" % (i + 1, train_perplexity))
            valid_perplexity = run_epoch(session, mvalid, dev_word, dev_tag, tf.no_op())
            print("Epoch: %d Valid Perplexity: %.3f" % (i + 1, valid_perplexity))
            test_perplexity = run_epoch_evaluate(session, mtest, test_word, test_tag, tf.no_op())
            print("Test Perplexity: %.3f" % test_perplexity)
        test_perplexity = run_epoch_evaluate(session, mtest, test_word, test_tag, tf.no_op())
        print("Test Perplexity: %.3f" % test_perplexity)


if __name__ == "__main__":
    tf.app.run()

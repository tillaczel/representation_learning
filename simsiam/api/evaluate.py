import os
import pytorch_lightning as pl
from omegaconf import DictConfig
import numpy as np
import wandb
import torch

from simsiam.data import get_linear_dataloaders
from simsiam.engine import LinearEngine
from simsiam.metrics import Metrics, get_accuracy


def evaluate(results, config: DictConfig):
    f_train, z_train, y_train, f_valid, z_valid, y_valid, f_test, z_test, y_test = results
    metrics = Metrics(config.dataset.n_classes, (1, 3, 5), knn_k=config.evaluation.knn.knn_k,
                      knn_t=config.evaluation.knn.knn_t)
    metrics_results = dict()
    for subset in [100, 10, 1]:
        if y_train.shape[0] == 40000:
            idx = np.genfromtxt(os.path.join(config.experiment.exp_dir, 'shuffle_index', 'idx_40000.csv'),
                                delimiter=',')
        elif y_train.shape[0] == 50000:
            idx = np.genfromtxt(os.path.join(config.experiment.exp_dir, 'shuffle_index', 'idx_50000.csv'),
                                delimiter=',')
        else:
            raise AssertionError('Training data not the right size')
        idx = idx[:int(idx.shape[0] * subset / 100)].astype(np.int32)
        _f_train, _z_train, _y_train = f_train[idx], z_train[idx], y_train[idx]

        _metrics_results = metrics.run(f_valid, z_valid, y_valid, _f_train, _z_train, _y_train)
        for k, v in _metrics_results.items():
            metrics_results[f'{subset}/{k}'] = v

        train_dataloader, valid_dataloader, test_dataloader = \
            get_linear_dataloaders(config.evaluation.linear,
                                   np.repeat(_f_train, int(100 / subset), axis=0),
                                   np.repeat(_z_train, int(100 / subset), axis=0),
                                   np.repeat(_y_train, int(100 / subset), axis=0),
                                   f_valid, z_valid, y_valid, f_test, z_test, y_test)
        engine = LinearEngine(config.evaluation.linear.in_dim, config.dataset.n_classes, config.evaluation.linear.lr,
                              config.evaluation.linear.momentum, config.evaluation.linear.weight_decay,
                              config.evaluation.linear.max_epochs, subset=subset)
        trainer = pl.Trainer(max_epochs=config.evaluation.linear.max_epochs,
                             deterministic=True,
                             terminate_on_nan=True,
                             num_sanity_val_steps=0,
                             gpus=config.experiment.gpu,
                             check_val_every_n_epoch=10
                             )
        trainer.fit(engine, train_dataloader, valid_dataloader)
        outputs = trainer.predict(engine, valid_dataloader)
        y_hat, y = map(torch.cat, zip(*outputs))

        _acc = get_accuracy(y_hat.numpy(), y.numpy(), (1, 3, 5))
        for k, v in _acc.items():
            metrics_results[f'{subset}/linear_{k}'] = v
    wandb.log(metrics_results)

    return metrics_results


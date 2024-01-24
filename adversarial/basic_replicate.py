# This script replicates the original D_rand and D_det experiments from Ilyas et al. (2019)
# It gets much better accuracy on D_rand (likely because we do not force all perturbations to
# reach the maximum radius), and worse on D_det (caused by using the smaller architecture).
"""
Training clean model...
Acc=1.0000(train),0.9365(test): 100%|█████████████████████████████| 200/200 [03:35<00:00,  1.08s/it]
Clean test accuracy: 0.9365
Generating D_rand...
100%|█████████████████████████████████████████████████████████████| 100/100 [01:51<00:00,  1.11s/it]
Fooling rate: 0.9367
Training on D_rand...
Acc=1.0000(train),0.8390(test): 100%|█████████████████████████████| 200/200 [03:33<00:00,  1.07s/it]
Clean test accuracy: 0.8390
Generating D_det...
100%|█████████████████████████████████████████████████████████████| 100/100 [01:51<00:00,  1.11s/it]
Fooling rate: 0.9271
Training on D_det...
Acc=1.0000(train),0.1981(test): 100%|█████████████████████████████| 200/200 [03:32<00:00,  1.06s/it]
Clean test accuracy: 0.1981
"""

import os
from tqdm import tqdm
import torch
import torch.nn.functional as F

from loader import CifarLoader
from model import make_net
from train import train, evaluate

loader = CifarLoader('cifar10', train=True, batch_size=500, shuffle=False, drop_last=False)

def pgd(inputs, targets, model, r=0.5, step_size=0.1, steps=100, eps=1e-5):
    delta = torch.zeros_like(inputs, requires_grad=True)
    norm_r = 4 * r # radius converted into normalized pixel space
    norm_step_size = 4 * step_size
    
    for step in range(steps):
        
        delta.grad = None
        output = model(inputs + delta)
        loss = F.cross_entropy(output, targets, reduction='none').sum()
        loss.backward()

        # normalize gradient
        grad_norm = delta.grad.reshape(len(delta), -1).norm(dim=1)
        unit_grad = delta.grad / (grad_norm[:, None, None, None] + eps)
        
        # take step in unit-gradient direction with scheduled step size
        delta.data -= norm_step_size * unit_grad

        # project to r-sphere
        delta_norm = delta.data.reshape(len(delta), -1).norm(dim=1)
        mask = (delta_norm >= norm_r)
        delta.data[mask] = norm_r * delta.data[mask] / (delta_norm[mask, None, None, None] + eps)
        # project to pixel-space
        delta.data = loader.normalize(loader.denormalize(inputs + delta.data).clip(0, 1)) - inputs

    return delta.data

## Generates D_rand, D_det, or D_other from the CIFAR-10 training set for a given model
def gen_adv_dataset(model, dtype='dother', **pgd_kwargs):
    assert dtype in ['drand', 'ddet', 'dother']
    loader = CifarLoader('/tmp/cifar10', train=True, batch_size=500, shuffle=False, drop_last=False)
    labels = loader.labels
    num_classes = 10
    if dtype == 'drand':
        loader.labels = torch.randint(num_classes, size=(len(labels),), device=labels.device)
    elif dtype == 'ddet':
        loader.labels = (labels + 1) % num_classes
    elif dtype == 'dother':
        labels_rotate = torch.randint(1, num_classes, size=(len(labels),), device=labels.device)
        loader.labels = (labels + labels_rotate) % num_classes
        
    inputs_adv = []
    for inputs, labels in tqdm(loader):
        delta = pgd(inputs, labels, model, **pgd_kwargs)
        inputs_adv.append(inputs + delta)
    inputs_adv = torch.cat(inputs_adv)

    loader.images = loader.denormalize(inputs_adv)
    print('Fooling rate: %.4f' % evaluate(model, loader))
    return loader


if __name__ == '__main__':

    os.makedirs('datasets', exist_ok=True)

    train_loader = CifarLoader('cifar10', train=True, aug=dict(flip=True, translate=4))
    test_loader = CifarLoader('cifar10', train=False)

    print('Training clean model...')
    model, _ = train(train_loader)
    print('Clean test accuracy: %.4f' % evaluate(model, test_loader))

    print('Generating D_rand...')
    loader = gen_adv_dataset(model, dtype='drand', r=0.5, step_size=0.1)
    loader.save('datasets/replicate_drand.pt')
    train_loader.load('datasets/replicate_drand.pt')
    print('Training on D_rand...')
    model1, _ = train(train_loader)
    print('Clean test accuracy: %.4f' % evaluate(model1, test_loader))

    print('Generating D_det...')
    loader = gen_adv_dataset(model, dtype='ddet', r=0.5, step_size=0.1)
    loader.save('datasets/replicate_ddet.pt')
    train_loader.load('datasets/replicate_ddet.pt')
    print('Training on D_det...')
    model1, _ = train(train_loader)
    print('Clean test accuracy: %.4f' % evaluate(model1, test_loader))


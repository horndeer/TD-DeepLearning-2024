# -*- coding: utf-8 -*-
#
# - read a custom image dataset
# - transfer learning (from resnet-18)
# - fine-tuning
#
# Useful link and source: https://pytorch.org/tutorials/beginner/transfer_learning_tutorial.html
# (Or more generally https://pytorch.org/tutorials/)
# Dataset from https://www.pyimagesearch.com/2019/01/14/machine-learning-in-python/
#              FlickrLogos: www.multimedia-computing.de/flickrlogos

import torch
import numpy as np
from sklearn.model_selection import train_test_split
import sys
from torchvision import datasets, transforms, models
import torch.nn as nn
import torch.optim as optim
import timm
import copy

# Normalisation des images pour les modèles pré-entraînés PyTorch
# voir: https://pytorch.org/docs/stable/torchvision/models.html
# et ici pour les « explications » sur les valeurs exactes: https://github.com/pytorch/vision/issues/1439
mean = np.array([0.485, 0.456, 0.406])
std = np.array([0.229, 0.224, 0.225])

data_transforms = transforms.Compose([
    transforms.Resize([224, 224]),
    transforms.ToTensor(),
    transforms.Normalize(mean=mean, std=std)
])

# on lit une première fois les images du dataset
# TODO adapter le path selon l'endroit où sont stockées les données
image_directory = "data/"
dataset_full = datasets.ImageFolder(image_directory, data_transforms)

# on split en train, val et test à partir de la liste complète
np.random.seed(42)
samples_train, samples_test = train_test_split(dataset_full.samples)
samples_train, samples_val = train_test_split(samples_train,test_size=0.2)

print("Nombre d'images de train : %i" % len(samples_train))
print("Nombre d'images de val : %i" % len(samples_val))
print("Nombre d'images de test : %i" % len(samples_test))

# on définit les datasets et loaders pytorch à partir des listes d'images de train / val / test
dataset_train = datasets.ImageFolder(image_directory, data_transforms)
dataset_train.samples = samples_train
dataset_train.imgs = samples_train
loader_train = torch.utils.data.DataLoader(dataset_train, batch_size=32, shuffle=True, num_workers=4)

dataset_val = datasets.ImageFolder(image_directory, data_transforms)
dataset_val.samples = samples_val
dataset_val.imgs = samples_val

dataset_test = datasets.ImageFolder(image_directory, data_transforms)
dataset_test.samples = samples_test
dataset_test.imgs = samples_test

torch.manual_seed(42)

# détermination du nombre de classes (nb_classes=6)
# vérification que les labels sont bien dans [0, nb_classes]
labels=[x[1] for x in samples_train]
if np.min(labels) != 0:
    print("Error: labels should start at 0 (min is %i)" % np.min(labels))
    sys.exit(-1)
if np.max(labels) != (len(np.unique(labels))-1):
    print("Error: labels should go from 0 to Nclasses (max label = {}; Nclasse = {})".format(np.max(labels),len(np.unique(labels)))  )
    sys.exit(-1)
nb_classes = np.max(labels)+1
# nb_classes = len(dataset_train.classes)
print("Apprentissage sur {} classes".format(nb_classes))

# on utilisera le GPU (beaucoup plus rapide) si disponible, sinon on utilisera le CPU
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
# device = torch.device("cpu") # forcer en CPU s'il y a des problèmes de mémoire GPU (+ être patient...)

# on définit une fonction d'évaluation
def evaluate(model, dataset):
    avg_loss = 0.
    avg_accuracy = 0
    loader = torch.utils.data.DataLoader(dataset, batch_size=16, shuffle=False, num_workers=2)
    for data in loader:
        inputs, labels = data
        inputs, labels = inputs.to(device), labels.to(device)
        outputs = model(inputs)
        
        loss = criterion(outputs, labels)
        _, preds = torch.max(outputs, 1)
        n_correct = torch.sum(preds == labels)
        
        avg_loss += loss.item()
        avg_accuracy += n_correct
        
    return avg_loss / len(dataset), float(avg_accuracy) / len(dataset)

# fonction classique d'entraînement d'un modèle, voir TDs précédents
PRINT_LOSS = True
def train_model(model, loader_train, data_val, optimizer, criterion, n_epochs=10):
    best_accuracy=0
    for epoch in range(n_epochs): # à chaque epochs
        print(f"EPOCH {epoch+1}")
        for i, data in enumerate(loader_train): # itère sur les minibatchs via le loader apprentissage
            inputs, labels = data
            inputs, labels = inputs.to(device), labels.to(device) # on passe les données sur CPU / GPU
            optimizer.zero_grad() # on réinitialise les gradients
            outputs = model(inputs) # on calcule l'output
            
            loss = criterion(outputs, labels) # on calcule la loss
            if PRINT_LOSS:
                model.train(False)
                loss_val, accuracy = evaluate(model, data_val)
                model.train(True)
                print("{} loss train: {:1.4f}\t val {:1.4f}\tAcc (val): {:.1%}".format(i, loss.item(), loss_val, accuracy))
                if accuracy > best_accuracy:
                    my_best_net = copy.deepcopy(model)
                    best_accuracy = accuracy
                    print(f'-- save model for best val accuracy {best_accuracy:.1%}')
            
            loss.backward() # on effectue la backprop pour calculer les gradients
            optimizer.step() # on update les gradients en fonction des paramètres
    return my_best_net

LEARNING_RATE=0.02
N_EPOCHS = 15
MOMENTUM = 0.9

# Récupérer un réseau pré-entraîné (resnet-18)
print("Récupération du ResNet-18 pré-entraîné...")
# my_net = models.resnet18(weights='ResNet18_Weights.IMAGENET1K_V1') # ou 'ResNet18_Weights.DEFAULT'
my_net = timm.create_model('resnet18.a1_in1k', pretrained=True, num_classes=6)

#===== Transfer learning "simple" (sans fine tuning) =====

# on indique qu'il est inutile de calculer les gradients des paramètres du réseau
for param in my_net.parameters():
    param.requires_grad = False

# on remplace la dernière couche fully connected à 1000 sorties (classes d'ImageNet) par une fully connected à 6 sorties (nos classes).
# par défaut, les gradients des paramètres cette couche seront bien calculés
my_net.fc = nn.Linear(in_features=my_net.fc.in_features, out_features=nb_classes, bias=True)
# on pourrait aussi réinitaliser d'autres couches telle: my_net.layer4[1].conv2
#  NB: par défaut, la couche réinitialisée a .requires_grad=True

my_net.to(device) # on utilise le GPU / CPU en fonction de ce qui est disponible
my_net.train(True) # pas indispensable ici, mais bonne pratique de façon générale
                   # permet notamment d'activer / désactiver le dropout selon qu'on entraîne ou teste le modèle

# définit loss + optimizer limité aux paramètres de la nouvelle couche
criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(my_net.fc.parameters(), lr=LEARNING_RATE, momentum=MOMENTUM)
# optimizer = optim.Adam(my_net.fc.parameters(), lr=LEARNING_RATE, amsgrad = True)

print("Apprentissage en transfer learning")
my_net.train(True)
torch.manual_seed(42)
my_best_net = train_model(my_net, loader_train, dataset_val, optimizer, criterion, n_epochs=N_EPOCHS)

# évaluation
my_best_net.train(False)
loss, accuracy = evaluate(my_best_net, dataset_test)
print(f"Accuracy (test): {accuracy:.1%}")

#===== Clean memory =====
import gc
my_net.cpu()
my_best_net.cpu()
del my_net, my_best_net
gc.collect()
torch.cuda.empty_cache()

#===== Fine tuning =====
# on réinitialise resnet
# my_net = models.resnet18(weights='ResNet18_Weights.IMAGENET1K_V1')
my_net_ft = timm.create_model('resnet18.a1_in1k', pretrained=True, num_classes=6)

my_net_ft.fc = nn.Linear(in_features=my_net_ft.fc.in_features, out_features=nb_classes, bias=True)
my_net_ft.to(device)

# cette fois on veut updater tous les paramètres
params_to_update = my_net_ft.parameters()

criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(params_to_update, lr=LEARNING_RATE, momentum=MOMENTUM)

# on ré-entraîne
print("Apprentissage avec fine-tuning")
my_net_ft.train(True)
torch.manual_seed(42)
my_best_net_ft = train_model(my_net_ft, loader_train, dataset_val, optimizer, criterion, n_epochs=N_EPOCHS)

# on ré-évalue les performances
my_best_net_ft.train(False)
loss, accuracy = evaluate(my_best_net_ft, dataset_test)
print(f"Accuracy (test): {accuracy:.1%}")

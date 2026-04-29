from speos.architectures import GeneNetwork, RelationalGeneNetwork, FCNN, LINKX, SimpleGCN
import torch
import torch.optim as optim
from speos.losses.approxndcg import approxNDCGLoss
from speos.losses.lambdaloss import lambdaLoss
from speos.losses.neuralndcg import neuralNDCGLoss
from speos.losses.unbiased import upu, nnpu
from speos.utils.path_utils import processed_data_path


class BaseModel:
    def __init__(self, config, dim, num_adjacencies):
        """Abstract class. Can host one or more Architectures (torch.nn.module classes) and extends forwardprop, backprop, optimizers etc. to those Architectures"""
        self.dim = dim
        self.num_adjacencies = num_adjacencies
        self.config = config
        self.loss_function = None
        self.architectures = self._architectures
        self.optimizers = [optim.Adam(self.architectures[i].parameters(), lr=config.optim.lr) for i in
                           range(self.num_archs)]
        self.losses = None
        self.reg_lambda = self.config.model.regularization_lambda
        self.available_losses = ["mse", "bce", "lambdaloss", "neuralndcg", "approxndcg", "upu", "nnpu"]
        self.requires_sgd = True
        self.training = True

    @property
    def _architectures(self):
        """loads architecture/s from config"""
        if type(self.config.model.architecture) == str:
            architectures = [self.get_architecture(self.config.model.architecture, self.dim) for _ in
                             range(self.num_archs)]
        elif type(self.config.model.architecture) == list:
            assert len(self.config.model.architecture) == self.num_archs
            architectures = [self.get_architecture(architecture, self.dim) for architecture in
                             self.config.model.architecture]
        else:
            raise ValueError

        return architectures

    def get_architecture(self, string, dim):
        if string == "GeneNetwork":
            if self.num_adjacencies > 1 or self.config.input.force_multigraph:
                print("---Multiple adjecencies---")
                return RelationalGeneNetwork(self.config, dim, self.num_adjacencies)
            else:
                print("---Single adjecency---")
                return GeneNetwork(self.config, dim)
        elif string == "FCNN":
            print("---FCNN---")
            return FCNN(self.config, dim)
        elif string == "LINKX":
            print("---LINXX---")
            return LINKX(self.config, dim)
        elif string == "SimpleGCN":
            print("---SimpleGCN---")
            return SimpleGCN(dim)

    def get_mp_layers(self):
        """ extracts and returns all message passing layers (graph convolutions)"""
        num_layers = self.config.model.mp.n_layers
        layers = []
        for architecture in self.architectures:
            every_n_th = len(architecture.mp._modules) / num_layers
            # modules = list(architecture.mp.named_modules())[0]
            _layers = [layer for i, layer in enumerate(architecture.mp._modules.values()) if i % every_n_th == 0]
            layers.extend(_layers)
        return layers

    def modules(self):
        return [architecture.modules() for architecture in self.architectures]

    def parameters(self):
        return [architecture.parameters() for architecture in self.architectures]

    def get_input_grads(self):
        return [architecture.input.grad for architecture in self.architectures]

    def __call__(self, *args, **kwargs):
        """hands input down to the pytorch forward methods for all implemented architectures of the model"""
        if len(self.architectures) == 1:
            return self.architectures[0](*args, **kwargs)
        else:
            return torch.stack([architecture(*args, **kwargs) for architecture in self.architectures], dim=0)

    def loss(self, *args, **kwargs):
        return self.loss_function(*args, **kwargs)

    def regularization(self):
        return torch.tensor([architecture.regularization() for architecture in self.architectures],
                            requires_grad=True).sum()

    def state_dict(self):
        return [architecture.state_dict() for architecture in self.architectures]

    def load_state_dict(self, state_dict: list):
        [self.architectures[i].load_state_dict(state_dict[i]) for i in range(len(state_dict))]

    def optimizer_step(self):
        [optimizer.step() for optimizer in self.optimizers]

    def optimizer_zero_grad(self):
        [optimizer.zero_grad() for optimizer in self.optimizers]

    def train(self, flag=True):
        [arch.train(flag) for arch in self.architectures]

    def eval(self):
        [arch.eval() for arch in self.architectures]

    def float(self):
        self.architectures = [arch for arch in self.architectures]
        return self

    def to(self, *args, **kwargs):
        self.architectures = [arch.to(*args, **kwargs) for arch in self.architectures]
        return self

    def loss_backward(self):
        [loss.backward() for loss in self.losses]

    def zero_grad(self):
        [arch.zero_grad() for arch in self.architectures]
        for arch in self.architectures:
            try:
                arch.input_grads = None
            except AttributeError:
                pass

    @property
    def input_grads(self):
        grads = []
        for architecture in self.architectures:
            try:
                grads.append(architecture.input_grads)
            except AttributeError:
                grads.append(None)

        return grads

    @property
    def final_conv_grads(self):
        grads = []
        for architecture in self.architectures:
            try:
                grads.append(architecture.final_conv_grads)
            except AttributeError:
                grads.append(None)

        return grads

    def balance_classes(self, items, truth):
        # assumes that truth has already been masked for training/eval
        positives = torch.nonzero(truth)
        negatives = torch.nonzero(1 - truth)

        dilution = 1 if self.config.training.dilution is None else self.config.training.dilution
        # return dilution times as many negatives as positives

        if dilution == "max" or (positives.shape[0] * dilution) >= negatives.shape[0]:
            sampled_negatives = negatives
            dilution = negatives.shape[0] / positives.shape[0]
        else:
            num_to_sample = positives.shape[0] * dilution
            sample_indices = torch.randint(0, negatives.shape[0], (num_to_sample,)).long()
            sampled_negatives = negatives[sample_indices]

        return items[positives], items[sampled_negatives], dilution


class SimpleModel(BaseModel):
    """ Implementation containing one straight forward torch.nn.module as architecture """

    def __init__(self, config, dim, num_adjacencies=1):
        self.num_archs = 1
        self.config = config

        self.one_hop_neighbors_dict = None
        self.two_hop_neighbors_dict = None
        self.three_hop_neighbors_dict = None

        super(SimpleModel, self).__init__(config, dim, num_adjacencies)
        if config.model.loss == "bce":
            self.loss_function = torch.nn.BCEWithLogitsLoss(reduction="none")
        elif config.model.loss == "mse":
            self.loss_function = torch.nn.MSELoss(reduction='none')
        elif config.model.loss == "lambdaloss":
            self.loss_function = lambdaLoss
        elif config.model.loss == "approxndcg":
            self.loss_function = approxNDCGLoss
        elif config.model.loss == "neuralndcg":
            self.loss_function = neuralNDCGLoss
        elif config.model.loss == "nnpu":
            self.loss_function = nnpu
        elif config.model.loss == "upu":
            self.loss_function = upu
        else:
            raise ValueError(
                "Specified loss {} not found in available losses: {}".format(config.model.loss, self.available_losses))

    def loss(self, output, truth):
        losses = self.loss_function(output, truth)
        pos_loss, neg_loss, dilution = self.balance_classes(losses, truth)

        pos_loss = pos_loss * self.config.training.pos_weight
        neg_loss = neg_loss / dilution

        loss = [torch.mean(torch.cat((pos_loss, neg_loss), dim=0))]

        self.losses = loss

        return self.losses

    def balance_losses(self, losses, truth):
        positive_losses, negative_losses, dilution = self.balance_classes(losses, truth)

        positive_losses = positive_losses * self.config.training.pos_weight
        negative_losses = negative_losses / dilution

        return torch.mean(torch.cat((positive_losses, negative_losses), dim=0))

    def convert_edge_index_dict(self, edge_index_dict):
        edge_index_list = []
        edge_type_list = []

        for edge_type, edge_index in enumerate(edge_index_dict.values()):
            edge_index_list.append(edge_index)
            edge_type_list.append(torch.full(edge_index.shape[1:], edge_type, dtype=torch.long))

        edge_index = torch.cat(edge_index_list, dim=1).to(self.config.device)
        edge_type = torch.cat(edge_type_list).to(self.config.device)

        return edge_index, edge_type

    def create_edge_attr(self, edge_index_dict):
        # Count the total number of edges in the graph
        num_edges = sum(edge_index.shape[1] for edge_index in edge_index_dict.values())

        # Initialize edge_attr tensor with the edge values
        # Here we are assuming that the edge values are 1
        edge_attr = torch.ones(num_edges, dtype=torch.float)

        return edge_attr

    def compute_one_two_hop_neighbors(self, edge_index_dict):
        from scipy.sparse import csr_matrix
        import numpy as np
        one_hop_neighbors_dict = {}
        two_hop_neighbors_dict = {}
        three_hop_neighbors_dict = {}
        for edge_type, edge_index in edge_index_dict.items():
            edge_index = edge_index.cpu().numpy()
            num_nodes = np.max(edge_index) + 1

            # Create adjacency matrix for the graph
            adj_matrix = csr_matrix((np.ones(edge_index.shape[1]), (edge_index[0], edge_index[1])),
                                    shape=(num_nodes, num_nodes))

            # Compute two-hop neighbors using matrix multiplication
            two_hop_matrix = adj_matrix.dot(adj_matrix)
            two_hop_matrix.setdiag(0)  # Remove self-loops
            two_hop_matrix.eliminate_zeros()

            three_hop_matrix = adj_matrix.dot(adj_matrix).dot(adj_matrix)
            three_hop_matrix.setdiag(0)  # Remove self-loops
            three_hop_matrix.eliminate_zeros()

            # Get one-hop neighbors
            one_hop_neighbors = [edge_index[1, edge_index[0] == node] for node in range(num_nodes)]
            one_hop_neighbors_dict[edge_type] = one_hop_neighbors
            two_hop_neighbors_dict[edge_type] = [two_hop_matrix[node].indices for node in range(num_nodes)]
            three_hop_neighbors_dict[edge_type] = [three_hop_matrix[node].indices for node in range(num_nodes)]

        return one_hop_neighbors_dict, two_hop_neighbors_dict, three_hop_neighbors_dict
    def neighbor_replace_2_hop_2(self, G, replace_prob=0.5):
        from scipy.sparse import csr_matrix
        import numpy as np

        """
        Function to randomly replace some edges with their 2-hop neighbors in a heterogeneous graph.
        Inspired by the paper: "Regularizing Graph Neural Networks via Consistency-Diversity
Graph Augmentations"
        Parameters:
        G (HeteroData): A heterogeneous graph data object.
        replace_prob (float): Probability with which to replace edges. Default is 0.5.

        Returns:
        HeteroData: A new heterogeneous graph with some edges replaced by 2-hop neighbors.
        """
        print("-----------neighbor_replace_2_hop_2-------------")
        edge_index_dict = G.edge_index_dict
        new_edges_dict = {}

        for edge_type, edge_index in edge_index_dict.items():
            edge_index = edge_index.cpu().numpy()
            num_nodes = np.max(edge_index) + 1

            if self.one_hop_neighbors_dict is None:
                self.one_hop_neighbors_dict, self.two_hop_neighbors_dict, self.three_hop_neighbors_dict = self.compute_one_two_hop_neighbors(edge_index_dict)
            one_hop_neighbors = self.one_hop_neighbors_dict[edge_type]
            two_hop_neighbors = self.two_hop_neighbors_dict[edge_type]
            # three_hop_neighbors = self.three_hop_neighbors_dict[edge_type]
            # Prepare to collect new edges
            new_edges = []

            for src in range(num_nodes):
                if one_hop_neighbors[src].size > 0:
                    # Determine if the edge should be replaced
                    mask = np.random.rand(one_hop_neighbors[src].size) < replace_prob
                    if mask.any():
                        possible_replacements = two_hop_neighbors[src]
                        if possible_replacements.size > 0:
                            replacements = np.random.choice(possible_replacements, size=mask.sum(), replace=True)
                            one_hop_neighbors[src][mask] = replacements
                    new_edges.append(
                        np.stack([np.full(one_hop_neighbors[src].size, src), one_hop_neighbors[src]], axis=0))

            if new_edges:
                new_edges = np.concatenate(new_edges, axis=1)
            else:
                new_edges = np.empty((2, 0), dtype=int)

            new_edges_dict[edge_type] = torch.tensor(new_edges, dtype=torch.long).contiguous()

        G_new = G.clone()
        G_new.edge_index_dict = new_edges_dict

        return G_new

    def step(self, data, mask, eval_flag=False, epoch=None):
        # print("---model step---")
        if eval_flag:
            self.training = False
            # print("---model mode : eval---")
            self.eval()
        else:
            self.training = True
            # print("---model mode : train---")
            self.train()

        self.zero_grad()
        
        # 1) forward pass
        # print("---1) forward pass ---")
        try:
            if self.config.model.mp.type == "rgat":
                # print("FP - rgat")
                edge_index, edge_type = self.convert_edge_index_dict(data.edge_index_dict)
                out = self(data.x, edge_index, edge_type=edge_type)
            elif self.config.model.mp.type == "filmedge":
                # print("Fp - filmedge")
                if not eval_flag and epoch >= 10:
                    # print("---train edges ON---")
                    train_edge = True
                else:
                    train_edge = False
                out = self(data.x, data.edge_index_dict, train_edge=train_edge)
            elif self.config.model.mp.type == "filmedge_2":
                # print("FP - filmedge_2")
                out = self(data.x, data.edge_index_dict, train_edge=True)
            elif self.config.model.mp.type == "film":
                print("FP - film")
                out = self(data.x, data.edge_index_dict)
                # data_augmented = self.neighbor_replace_2_hop_2(data)
                # edge_index_augmented, edge_type_augmented = self.convert_edge_index_dict(data_augmented.edge_index_dict)
                # out_augmented = self(data_augmented.x, data_augmented.edge_index_dict )
            else:
                print("FP - any other model")
                out = self(data.x, data.edge_index_dict)
        except AttributeError as e:
            out = self(data.x_dict, data.edge_index_dict)
            if type(out) == dict:
                keys = list(out.keys())
                assert len(
                    keys) == 1, "More than one node type passed, this implementation is built with only one node type in mind."
                out = out[keys[0]]
                
        # 2) loss computation
        # print("---2) loss computation ---")
        if self.config.model.mp.type == "film":
            loss = self.loss_function(out[mask].squeeze(), data.y[mask].squeeze()).squeeze()
            # loss = self.loss_function(out_augmented[mask].squeeze(), data.y[mask].squeeze()).squeeze()
            # loss_mse = torch.nn.MSELoss()(out[mask].squeeze(), out_augmented[mask].squeeze()).squeeze()
            # loss = loss + loss_mse
        else:
            loss = self.loss_function(out[mask].squeeze(), data.y[mask].squeeze()).squeeze()

        if len(loss.shape) > 0:
            loss = self.balance_losses(loss, data.y[mask])

        if not eval_flag:
            # reg_loss = self.reg_lambda * self.regularization()
            try:
                # quick but dirty implementation to regularize linkx, throws attributeError for other archs, which is caught silently
                reg_loss = self.reg_lambda * self.architectures[-1].mlp_a[0].weight.norm(1)
                loss += reg_loss
            except AttributeError:
                pass
            except Exception as e:
                print("An error occurred:", e)
                
            # 3) backward pass
            # print("---3) backward pass ---")
            loss.backward()
            # 4) optimizing parameters
            # print("---4) optimizing parameters---")
            self.optimizer_step()

        self.losses = [loss]

        return out.reshape(1, -1), loss.item()


class AdversarialModel(BaseModel):
    """ Implementation containing two torch.nn.module as architectures. Architectures are incentivised against each other. """

    def __init__(self, config, dim):
        self.num_archs = 2
        super(AdversarialModel, self).__init__(config, dim)
        self.burn_in = 10  # config.model.burn_in
        self._lambda = 0.1
        self.classifier = self.architectures[0]
        self.discriminator = self.architectures[1]
        self.opt_classifier = self.optimizers[0]
        self.opt_discriminator = self.optimizers[1]

    def step(self, data, mask, eval_flag=False):
        if eval_flag:
            self.eval()
        else:
            self.discriminator.train()

        self.opt_discriminator.zero_grad()
        self.opt_classifier.zero_grad()

        logit_out = self(data.x, data.edge_index)[:, mask, :]
        out = torch.sigmoid(logit_out)
        out_classifier = out[0, :].squeeze()
        out_discriminator = out[1, :].squeeze()

        discriminator_out_pos, sampled_discriminator_out_unlabeled, dilution = self.balance_classes(out_discriminator,
                                                                                                    data.y[mask])
        _, sampled_classifier_out_unlabeled, dilution = self.balance_classes(out_classifier, data.y[mask])
        disc_loss = - self.discriminator_loss(discriminator_out_pos, sampled_discriminator_out_unlabeled,
                                              sampled_classifier_out_unlabeled, dilution)
        if not eval_flag:
            disc_loss.backward()
            self.opt_discriminator.step()

        if self.burn_in <= 0:
            if not eval_flag:
                self.discriminator.train(False)
                self.classifier.train()
            self.opt_discriminator.zero_grad()
            self.opt_classifier.zero_grad()
            logit_out = self(data.x, data.edge_index)[:, mask, :]
            out = torch.sigmoid(logit_out)
            out_classifier = out[0, :].squeeze()
            out_discriminator = out[1, :].squeeze()

            discriminator_out_pos, sampled_discriminator_out_unlabeled, dilution = self.balance_classes(
                out_discriminator, data.y[mask])
            _, sampled_classifier_out_unlabeled, dilution = self.balance_classes(out_classifier, data.y[mask])
            class_loss = self.classifier_loss(sampled_discriminator_out_unlabeled, sampled_classifier_out_unlabeled,
                                              dilution)
            if not eval_flag:
                class_loss.backward()
                self.opt_classifier.step()

        else:
            class_loss = torch.zeros_like(disc_loss)
            self.burn_in -= 1

        self.losses = [class_loss, disc_loss]

        return logit_out, [class_loss, disc_loss]

    def discriminator_loss(self, discriminator_out_pos, discriminator_out_unlabeled, classifier_out_unlabeled,
                           dilution):
        first_term_pos = torch.sum(torch.log(discriminator_out_pos + 1e-16))
        first_term_unlabeled = torch.sum(torch.log(1 - discriminator_out_unlabeled + 1e-16)) / dilution
        second_term = self.classifier_loss(discriminator_out_unlabeled, classifier_out_unlabeled, dilution)
        # second_term = torch.sum(torch.mul(torch.sub(torch.log(1-classifier_out_unlabeled),torch.log(classifier_out_unlabeled)),(2*discriminator_out_unlabeled)-1)) / dilution
        return torch.sum(torch.stack((first_term_pos, first_term_unlabeled, second_term)))

    def classifier_loss(self, discriminator_out_unlabeled, classifier_out_unlabeled, dilution):
        left_side = torch.sub(torch.log(1 - classifier_out_unlabeled + 1e-16),
                              torch.log(classifier_out_unlabeled + 1e-16))
        right_side = (2 * discriminator_out_unlabeled) - 1
        return torch.sum(torch.mul(self._lambda * left_side, right_side)) / dilution

    def loss_backward(self):
        if self.burn_in > 0:
            self.losses[1].backward()
        else:
            [loss.backward for loss in self.losses]

    def backprop_and_optimizer_step(self):
        # deprecated

        classifier_loss = self.losses[0]
        discriminator_loss = self.losses[1]

        # update discriminator
        self.zero_grad()
        self.classifier.train(False)
        self.discriminator.train(True)
        discriminator_loss.backward()
        self.opt_discriminator.step()

        # update classifier
        self.zero_grad()
        self.classifier.train(True)
        self.discriminator.train(False)
        classifier_loss.backward()
        self.opt_classifier.step()


class ModelBootstrapper:
    def __init__(self, config, dim, num_adjacencies=1):
        if config.model.model == "AdversarialModel":
            self.model = AdversarialModel(config, dim)
        elif config.model.model == "SimpleModel":
            self.model = SimpleModel(config, dim, num_adjacencies)
        elif config.model.model == "LogisticRegressionModel":
            self.model = LogisticRegressionModel(config)
        elif config.model.model == "RandomForestModel":
            self.model = RandomForestModel(config)
        elif config.model.model == "SupportVectorModel":
            self.model = SupportVectorModel(config)
        elif config.model.model.lower() == "rwrm":
            self.model = RWRM(config)
        else:
            raise ValueError("The model you requested '{}' is not implemented.".format(config.model.model))

    def get_model(self):
        return self.model


class SKLearnModel:
    """ Interface to seamlessly fit sklearn models into this framework for easier comparison"""

    def __init__(self, model, config, *args, **kwargs):
        self.model = model(*config.model.args, *args, **config.model.kwargs, **kwargs)
        self.pos_weight = config.training.pos_weight
        self.config = config
        self.architectures = [self]
        self.requires_sgd = False

    def to(self, *args, **kwargs):
        return self

    def step(self, data, mask, eval_flag=False):
        import numpy as np
        sample_weight = np.ones_like(data.y[mask].detach().cpu().numpy())
        sample_weight[data.y[mask].detach().cpu().numpy().astype(np.bool8)] = self.pos_weight

        if not eval_flag:
            if self.pos_weight is None:
                self.model.fit(data.x[mask].detach().cpu().numpy(), data.y[mask].detach().cpu().numpy())
            else:
                self.model.fit(data.x[mask].detach().cpu().numpy(), data.y[mask].detach().cpu().numpy(),
                               sample_weight=sample_weight)

        out = self.model.predict_log_proba(data.x.detach().cpu().numpy())
        accuracy = self.model.score(data.x[mask].detach().cpu().numpy(), data.y[mask].detach().cpu().numpy(),
                                    sample_weight=sample_weight)

        return torch.Tensor(out[:, 1].reshape((1, -1))), 1 - accuracy

    def state_dict(self):
        from pickle import dumps
        return dumps(self.model)

    def load_state_dict(self, state_dict):
        from pickle import loads
        self.model = loads(state_dict)


class LogisticRegressionModel(SKLearnModel):
    def __init__(self, config, *args, **kwargs):
        from sklearn.linear_model import LogisticRegression
        if "max_iter" not in kwargs.keys():
            kwargs.update({"max_iter": 100000})
        super(LogisticRegressionModel, self).__init__(model=LogisticRegression, config=config, class_weight="balanced",
                                                      *args, **kwargs)


class RandomForestModel(SKLearnModel):
    def __init__(self, config, *args, **kwargs):
        from sklearn.ensemble import RandomForestClassifier
        super(RandomForestModel, self).__init__(model=RandomForestClassifier, config=config,
                                                class_weight="balanced_subsample", *args, **kwargs)


class SupportVectorModel(SKLearnModel):
    def __init__(self, config, *args, **kwargs):
        from sklearn.svm import SVC
        super(SupportVectorModel, self).__init__(model=SVC, config=config, probability=True, class_weight="balanced",
                                                 *args, **kwargs)


class RWRM:
    def __init__(self, config, *args, **kwargs):
        self.config = config
        self.results = None
        self.architectures = [self]
        self.requires_sgd = False

    def to(self, *args, **kwargs):
        return self

    def step(self, *args, eval_flag=False):
        import subprocess
        import pandas as pd
        import numpy as np
        import os
        rwr_path = "./RWR-M"
        input_file = self.config.name
        output_file = input_file + "_results"
        eps = 1e-16
        data = pd.read_csv(processed_data_path(self.config)[1], header=0, sep="\t")

        if not eval_flag:
            true_training_hgnc = data["hgnc"][
                (data["truth"].values.astype(np.bool8) & data["train"].values.astype(np.bool8))]
            true_training_hgnc.to_csv(os.path.join(rwr_path, input_file), header=False, index=False)
            model_parameters = "Parameters_Example.txt" if "parameters" not in self.config.model.kwargs.keys() else \
            self.config.model.kwargs["parameters"]

            call = 'source ~/anaconda3/etc/profile.d/conda.sh && conda activate rwr && cd {} && Rscript RWR-M.R {}  Input_Files/{} {}'.format(
                rwr_path, input_file, model_parameters, output_file
            )
            p1 = subprocess.Popen([call], shell=True)
            p1.wait()

            results = pd.read_csv(os.path.join(rwr_path, "Output_Files", output_file + ".txt"), header=0, sep="\t",
                                  index_col=0)

            final_results = data.join(results, on="hgnc", how="left").replace(np.nan, 0)

            self.results = final_results["Score"].values + eps

        return torch.Tensor(self.results.reshape((1, -1))), np.nan

    def state_dict(self):
        from pickle import dumps
        return dumps(self.results)

    def load_state_dict(self, state_dict):
        from pickle import loads
        self.results = loads(state_dict)

# TODO TransE, ComplEx, Node2Vec


# from speos.architectures import GeneNetwork, RelationalGeneNetwork, FCNN, LINKX, SimpleGCN
# import torch
# import torch.optim as optim
# from speos.losses.approxndcg import approxNDCGLoss
# from speos.losses.lambdaloss import lambdaLoss
# from speos.losses.neuralndcg import neuralNDCGLoss
# from speos.losses.unbiased import upu, nnpu
# from speos.utils.path_utils import processed_data_path


# class BaseModel:
#     def __init__(self, config, dim, num_adjacencies):
#         """Abstract class. Can host one or more Architectures (torch.nn.module classes) and extends forwardprop, backprop, optimizers etc. to those Architectures"""
#         self.dim = dim
#         self.num_adjacencies = num_adjacencies
#         self.config = config
#         self.loss_function = None
#         self.architectures = self._architectures
#         self.optimizers = [optim.Adam(self.architectures[i].parameters(), lr=config.optim.lr) for i in
#                            range(self.num_archs)]
#         self.losses = None
#         self.reg_lambda = self.config.model.regularization_lambda
#         self.available_losses = ["mse", "bce", "lambdaloss", "neuralndcg", "approxndcg", "upu", "nnpu"]
#         self.requires_sgd = True
#         self.training = True

#     @property
#     def _architectures(self):
#         """loads architecture/s from config"""
#         if type(self.config.model.architecture) == str:
#             architectures = [self.get_architecture(self.config.model.architecture, self.dim) for _ in
#                              range(self.num_archs)]
#         elif type(self.config.model.architecture) == list:
#             assert len(self.config.model.architecture) == self.num_archs
#             architectures = [self.get_architecture(architecture, self.dim) for architecture in
#                              self.config.model.architecture]
#         else:
#             raise ValueError

#         return architectures

#     def get_architecture(self, string, dim):
#         if string == "GeneNetwork":
#             if self.num_adjacencies > 1 or self.config.input.force_multigraph:
#                 print("---Multiple adjecencies---")
#                 return RelationalGeneNetwork(self.config, dim, self.num_adjacencies)
#             else:
#                 print("---Single adjecency---")
#                 return GeneNetwork(self.config, dim)
#         elif string == "FCNN":
#             print("---FCNN---")
#             return FCNN(self.config, dim)
#         elif string == "LINKX":
#             print("---LINXX---")
#             return LINKX(self.config, dim)
#         elif string == "SimpleGCN":
#             print("---SimpleGCN---")
#             return SimpleGCN(dim)

#     def get_mp_layers(self):
#         """ extracts and returns all message passing layers (graph convolutions)"""
#         num_layers = self.config.model.mp.n_layers
#         layers = []
#         for architecture in self.architectures:
#             every_n_th = len(architecture.mp._modules) / num_layers
#             # modules = list(architecture.mp.named_modules())[0]
#             _layers = [layer for i, layer in enumerate(architecture.mp._modules.values()) if i % every_n_th == 0]
#             layers.extend(_layers)
#         return layers

#     def modules(self):
#         return [architecture.modules() for architecture in self.architectures]

#     def parameters(self):
#         return [architecture.parameters() for architecture in self.architectures]

#     def get_input_grads(self):
#         return [architecture.input.grad for architecture in self.architectures]

#     def __call__(self, *args, **kwargs):
#         """hands input down to the pytorch forward methods for all implemented architectures of the model"""
#         if len(self.architectures) == 1:
#             return self.architectures[0](*args, **kwargs)
#         else:
#             return torch.stack([architecture(*args, **kwargs) for architecture in self.architectures], dim=0)

#     def loss(self, *args, **kwargs):
#         return self.loss_function(*args, **kwargs)

#     def regularization(self):
#         return torch.tensor([architecture.regularization() for architecture in self.architectures],
#                             requires_grad=True).sum()

#     def state_dict(self):
#         return [architecture.state_dict() for architecture in self.architectures]

#     def load_state_dict(self, state_dict: list):
#         [self.architectures[i].load_state_dict(state_dict[i]) for i in range(len(state_dict))]

#     def optimizer_step(self):
#         [optimizer.step() for optimizer in self.optimizers]

#     def optimizer_zero_grad(self):
#         [optimizer.zero_grad() for optimizer in self.optimizers]

#     def train(self, flag=True):
#         [arch.train(flag) for arch in self.architectures]

#     def eval(self):
#         [arch.eval() for arch in self.architectures]

#     def float(self):
#         self.architectures = [arch for arch in self.architectures]
#         return self

#     def to(self, *args, **kwargs):
#         self.architectures = [arch.to(*args, **kwargs) for arch in self.architectures]
#         return self

#     def loss_backward(self):
#         [loss.backward() for loss in self.losses]

#     def zero_grad(self):
#         [arch.zero_grad() for arch in self.architectures]
#         for arch in self.architectures:
#             try:
#                 arch.input_grads = None
#             except AttributeError:
#                 pass

#     @property
#     def input_grads(self):
#         grads = []
#         for architecture in self.architectures:
#             try:
#                 grads.append(architecture.input_grads)
#             except AttributeError:
#                 grads.append(None)

#         return grads

#     @property
#     def final_conv_grads(self):
#         grads = []
#         for architecture in self.architectures:
#             try:
#                 grads.append(architecture.final_conv_grads)
#             except AttributeError:
#                 grads.append(None)

#         return grads

#     def balance_classes(self, items, truth):
#         # assumes that truth has already been masked for training/eval
#         positives = torch.nonzero(truth)
#         negatives = torch.nonzero(1 - truth)

#         dilution = 1 if self.config.training.dilution is None else self.config.training.dilution
#         # return dilution times as many negatives as positives

#         if dilution == "max" or (positives.shape[0] * dilution) >= negatives.shape[0]:
#             sampled_negatives = negatives
#             dilution = negatives.shape[0] / positives.shape[0]
#         else:
#             num_to_sample = positives.shape[0] * dilution
#             sample_indices = torch.randint(0, negatives.shape[0], (num_to_sample,)).long()
#             sampled_negatives = negatives[sample_indices]

#         return items[positives], items[sampled_negatives], dilution


# class SimpleModel(BaseModel):
#     """ Implementation containing one straight forward torch.nn.module as architecture """

#     def __init__(self, config, dim, num_adjacencies=1):
#         self.num_archs = 1
#         self.config = config

#         self.one_hop_neighbors_dict = None
#         self.two_hop_neighbors_dict = None
#         self.three_hop_neighbors_dict = None

#         super(SimpleModel, self).__init__(config, dim, num_adjacencies)
#         if config.model.loss == "bce":
#             self.loss_function = torch.nn.BCEWithLogitsLoss(reduction="none")
#         elif config.model.loss == "mse":
#             self.loss_function = torch.nn.MSELoss(reduction='none')
#         elif config.model.loss == "lambdaloss":
#             self.loss_function = lambdaLoss
#         elif config.model.loss == "approxndcg":
#             self.loss_function = approxNDCGLoss
#         elif config.model.loss == "neuralndcg":
#             self.loss_function = neuralNDCGLoss
#         elif config.model.loss == "nnpu":
#             self.loss_function = nnpu
#         elif config.model.loss == "upu":
#             self.loss_function = upu
#         else:
#             raise ValueError(
#                 "Specified loss {} not found in available losses: {}".format(config.model.loss, self.available_losses))

#     def loss(self, output, truth):
#         losses = self.loss_function(output, truth)
#         pos_loss, neg_loss, dilution = self.balance_classes(losses, truth)

#         pos_loss = pos_loss * self.config.training.pos_weight
#         neg_loss = neg_loss / dilution

#         loss = [torch.mean(torch.cat((pos_loss, neg_loss), dim=0))]

#         self.losses = loss

#         return self.losses

#     def balance_losses(self, losses, truth):
#         positive_losses, negative_losses, dilution = self.balance_classes(losses, truth)

#         positive_losses = positive_losses * self.config.training.pos_weight
#         negative_losses = negative_losses / dilution

#         return torch.mean(torch.cat((positive_losses, negative_losses), dim=0))

#     def convert_edge_index_dict(self, edge_index_dict):
#         edge_index_list = []
#         edge_type_list = []

#         for edge_type, edge_index in enumerate(edge_index_dict.values()):
#             edge_index_list.append(edge_index)
#             edge_type_list.append(torch.full(edge_index.shape[1:], edge_type, dtype=torch.long))

#         edge_index = torch.cat(edge_index_list, dim=1).to(self.config.device)
#         edge_type = torch.cat(edge_type_list).to(self.config.device)

#         return edge_index, edge_type

#     def create_edge_attr(self, edge_index_dict):
#         # Count the total number of edges in the graph
#         num_edges = sum(edge_index.shape[1] for edge_index in edge_index_dict.values())

#         # Initialize edge_attr tensor with the edge values
#         # Here we are assuming that the edge values are 1
#         edge_attr = torch.ones(num_edges, dtype=torch.float)

#         return edge_attr

#     def compute_one_two_hop_neighbors(self, edge_index_dict):
#         from scipy.sparse import csr_matrix
#         import numpy as np
#         one_hop_neighbors_dict = {}
#         two_hop_neighbors_dict = {}
#         three_hop_neighbors_dict = {}
#         for edge_type, edge_index in edge_index_dict.items():
#             edge_index = edge_index.cpu().numpy()
#             num_nodes = np.max(edge_index) + 1

#             # Create adjacency matrix for the graph
#             adj_matrix = csr_matrix((np.ones(edge_index.shape[1]), (edge_index[0], edge_index[1])),
#                                     shape=(num_nodes, num_nodes))

#             # Compute two-hop neighbors using matrix multiplication
#             two_hop_matrix = adj_matrix.dot(adj_matrix)
#             two_hop_matrix.setdiag(0)  # Remove self-loops
#             two_hop_matrix.eliminate_zeros()

#             three_hop_matrix = adj_matrix.dot(adj_matrix).dot(adj_matrix)
#             three_hop_matrix.setdiag(0)  # Remove self-loops
#             three_hop_matrix.eliminate_zeros()

#             # Get one-hop neighbors
#             one_hop_neighbors = [edge_index[1, edge_index[0] == node] for node in range(num_nodes)]
#             one_hop_neighbors_dict[edge_type] = one_hop_neighbors
#             two_hop_neighbors_dict[edge_type] = [two_hop_matrix[node].indices for node in range(num_nodes)]
#             three_hop_neighbors_dict[edge_type] = [three_hop_matrix[node].indices for node in range(num_nodes)]

#         return one_hop_neighbors_dict, two_hop_neighbors_dict, three_hop_neighbors_dict
#     def neighbor_replace_2_hop_2(self, G, replace_prob=0.5):
#         from scipy.sparse import csr_matrix
#         import numpy as np

#         """
#         Function to randomly replace some edges with their 2-hop neighbors in a heterogeneous graph.
#         Inspired by the paper: "Regularizing Graph Neural Networks via Consistency-Diversity
# Graph Augmentations"
#         Parameters:
#         G (HeteroData): A heterogeneous graph data object.
#         replace_prob (float): Probability with which to replace edges. Default is 0.5.

#         Returns:
#         HeteroData: A new heterogeneous graph with some edges replaced by 2-hop neighbors.
#         """
#         print("-----------neighbor_replace_2_hop_2-------------")
#         edge_index_dict = G.edge_index_dict
#         new_edges_dict = {}

#         for edge_type, edge_index in edge_index_dict.items():
#             edge_index = edge_index.cpu().numpy()
#             num_nodes = np.max(edge_index) + 1

#             if self.one_hop_neighbors_dict is None:
#                 self.one_hop_neighbors_dict, self.two_hop_neighbors_dict, self.three_hop_neighbors_dict = self.compute_one_two_hop_neighbors(edge_index_dict)
#             one_hop_neighbors = self.one_hop_neighbors_dict[edge_type]
#             two_hop_neighbors = self.two_hop_neighbors_dict[edge_type]
#             # three_hop_neighbors = self.three_hop_neighbors_dict[edge_type]
#             # Prepare to collect new edges
#             new_edges = []

#             for src in range(num_nodes):
#                 if one_hop_neighbors[src].size > 0:
#                     # Determine if the edge should be replaced
#                     mask = np.random.rand(one_hop_neighbors[src].size) < replace_prob
#                     if mask.any():
#                         possible_replacements = two_hop_neighbors[src]
#                         if possible_replacements.size > 0:
#                             replacements = np.random.choice(possible_replacements, size=mask.sum(), replace=True)
#                             one_hop_neighbors[src][mask] = replacements
#                     new_edges.append(
#                         np.stack([np.full(one_hop_neighbors[src].size, src), one_hop_neighbors[src]], axis=0))

#             if new_edges:
#                 new_edges = np.concatenate(new_edges, axis=1)
#             else:
#                 new_edges = np.empty((2, 0), dtype=int)

#             new_edges_dict[edge_type] = torch.tensor(new_edges, dtype=torch.long).contiguous()

#         G_new = G.clone()
#         G_new.edge_index_dict = new_edges_dict

#         return G_new

#     def step(self, data, mask, eval_flag=False, epoch=None):
#         # print("---model step---")
#         if eval_flag:
#             self.training = False
#             # print("---model mode : eval---")
#             self.eval()
#         else:
#             self.training = True
#             # print("---model mode : train---")
#             self.train()

#         self.zero_grad()
        
#         # 1) forward pass
#         # print("---1) forward pass ---")
#         try:
#             if self.config.model.mp.type == "rgat":
#                 # print("FP - rgat")
#                 edge_index, edge_type = self.convert_edge_index_dict(data.edge_index_dict)
#                 out = self(data.x, edge_index, edge_type=edge_type)
#             elif self.config.model.mp.type == "filmedge":
#                 # print("Fp - filmedge")
#                 if not eval_flag and epoch >= 10:
#                     # print("---train edges ON---")
#                     train_edge = True
#                 else:
#                     train_edge = False
#                 out = self(data.x, data.edge_index_dict, train_edge=train_edge)
#             elif self.config.model.mp.type == "filmedge_2":
#                 # print("FP - filmedge_2")
#                 out = self(data.x, data.edge_index_dict, train_edge=True)
#             elif self.config.model.mp.type == "film" or self.config.model.mp.type == "filmfilm": #filmfilm added later
#                 print("FP - film")
#                 out = self(data.x, data.edge_index_dict)
#                 # data_augmented = self.neighbor_replace_2_hop_2(data)
#                 # edge_index_augmented, edge_type_augmented = self.convert_edge_index_dict(data_augmented.edge_index_dict)
#                 # out_augmented = self(data_augmented.x, data_augmented.edge_index_dict )
#             else:
#                 print("FP - any other model")
#                 out = self(data.x, data.edge_index_dict)
#         except AttributeError as e:
#             out = self(data.x_dict, data.edge_index_dict)
#             if type(out) == dict:
#                 keys = list(out.keys())
#                 assert len(
#                     keys) == 1, "More than one node type passed, this implementation is built with only one node type in mind."
#                 out = out[keys[0]]
                
#         # 2) loss computation
#         # print("---2) loss computation ---")
#         if self.config.model.mp.type == "film" or self.config.model.mp.type == "filmfilm": #filmfilm added later
#             loss = self.loss_function(out[mask].squeeze(), data.y[mask].squeeze()).squeeze()
#             # loss = self.loss_function(out_augmented[mask].squeeze(), data.y[mask].squeeze()).squeeze()
#             # loss_mse = torch.nn.MSELoss()(out[mask].squeeze(), out_augmented[mask].squeeze()).squeeze()
#             # loss = loss + loss_mse
#         else:
#             loss = self.loss_function(out[mask].squeeze(), data.y[mask].squeeze()).squeeze()

#         if len(loss.shape) > 0:
#             loss = self.balance_losses(loss, data.y[mask])

#         if not eval_flag:
#             # reg_loss = self.reg_lambda * self.regularization()
#             try:
#                 # quick but dirty implementation to regularize linkx, throws attributeError for other archs, which is caught silently
#                 reg_loss = self.reg_lambda * self.architectures[-1].mlp_a[0].weight.norm(1)
#                 loss += reg_loss
#             except AttributeError:
#                 pass
#             except Exception as e:
#                 print("An error occurred:", e)
                
#             # 3) backward pass
#             # print("---3) backward pass ---")
#             loss.backward()
#             # 4) optimizing parameters
#             # print("---4) optimizing parameters---")
#             self.optimizer_step()

#         self.losses = [loss]

#         return out.reshape(1, -1), loss.item()


# class AdversarialModel(BaseModel):
#     """ Implementation containing two torch.nn.module as architectures. Architectures are incentivised against each other. """

#     def __init__(self, config, dim):
#         self.num_archs = 2
#         super(AdversarialModel, self).__init__(config, dim)
#         self.burn_in = 10  # config.model.burn_in
#         self._lambda = 0.1
#         self.classifier = self.architectures[0]
#         self.discriminator = self.architectures[1]
#         self.opt_classifier = self.optimizers[0]
#         self.opt_discriminator = self.optimizers[1]

#     def step(self, data, mask, eval_flag=False):
#         if eval_flag:
#             self.eval()
#         else:
#             self.discriminator.train()

#         self.opt_discriminator.zero_grad()
#         self.opt_classifier.zero_grad()

#         logit_out = self(data.x, data.edge_index)[:, mask, :]
#         out = torch.sigmoid(logit_out)
#         out_classifier = out[0, :].squeeze()
#         out_discriminator = out[1, :].squeeze()

#         discriminator_out_pos, sampled_discriminator_out_unlabeled, dilution = self.balance_classes(out_discriminator,
#                                                                                                     data.y[mask])
#         _, sampled_classifier_out_unlabeled, dilution = self.balance_classes(out_classifier, data.y[mask])
#         disc_loss = - self.discriminator_loss(discriminator_out_pos, sampled_discriminator_out_unlabeled,
#                                               sampled_classifier_out_unlabeled, dilution)
#         if not eval_flag:
#             disc_loss.backward()
#             self.opt_discriminator.step()

#         if self.burn_in <= 0:
#             if not eval_flag:
#                 self.discriminator.train(False)
#                 self.classifier.train()
#             self.opt_discriminator.zero_grad()
#             self.opt_classifier.zero_grad()
#             logit_out = self(data.x, data.edge_index)[:, mask, :]
#             out = torch.sigmoid(logit_out)
#             out_classifier = out[0, :].squeeze()
#             out_discriminator = out[1, :].squeeze()

#             discriminator_out_pos, sampled_discriminator_out_unlabeled, dilution = self.balance_classes(
#                 out_discriminator, data.y[mask])
#             _, sampled_classifier_out_unlabeled, dilution = self.balance_classes(out_classifier, data.y[mask])
#             class_loss = self.classifier_loss(sampled_discriminator_out_unlabeled, sampled_classifier_out_unlabeled,
#                                               dilution)
#             if not eval_flag:
#                 class_loss.backward()
#                 self.opt_classifier.step()

#         else:
#             class_loss = torch.zeros_like(disc_loss)
#             self.burn_in -= 1

#         self.losses = [class_loss, disc_loss]

#         return logit_out, [class_loss, disc_loss]

#     def discriminator_loss(self, discriminator_out_pos, discriminator_out_unlabeled, classifier_out_unlabeled,
#                            dilution):
#         first_term_pos = torch.sum(torch.log(discriminator_out_pos + 1e-16))
#         first_term_unlabeled = torch.sum(torch.log(1 - discriminator_out_unlabeled + 1e-16)) / dilution
#         second_term = self.classifier_loss(discriminator_out_unlabeled, classifier_out_unlabeled, dilution)
#         # second_term = torch.sum(torch.mul(torch.sub(torch.log(1-classifier_out_unlabeled),torch.log(classifier_out_unlabeled)),(2*discriminator_out_unlabeled)-1)) / dilution
#         return torch.sum(torch.stack((first_term_pos, first_term_unlabeled, second_term)))

#     def classifier_loss(self, discriminator_out_unlabeled, classifier_out_unlabeled, dilution):
#         left_side = torch.sub(torch.log(1 - classifier_out_unlabeled + 1e-16),
#                               torch.log(classifier_out_unlabeled + 1e-16))
#         right_side = (2 * discriminator_out_unlabeled) - 1
#         return torch.sum(torch.mul(self._lambda * left_side, right_side)) / dilution

#     def loss_backward(self):
#         if self.burn_in > 0:
#             self.losses[1].backward()
#         else:
#             [loss.backward for loss in self.losses]

#     def backprop_and_optimizer_step(self):
#         # deprecated

#         classifier_loss = self.losses[0]
#         discriminator_loss = self.losses[1]

#         # update discriminator
#         self.zero_grad()
#         self.classifier.train(False)
#         self.discriminator.train(True)
#         discriminator_loss.backward()
#         self.opt_discriminator.step()

#         # update classifier
#         self.zero_grad()
#         self.classifier.train(True)
#         self.discriminator.train(False)
#         classifier_loss.backward()
#         self.opt_classifier.step()


# class ModelBootstrapper:
#     def __init__(self, config, dim, num_adjacencies=1):
#         if config.model.model == "AdversarialModel":
#             self.model = AdversarialModel(config, dim)
#         elif config.model.model == "SimpleModel":
#             self.model = SimpleModel(config, dim, num_adjacencies)
#         elif config.model.model == "LogisticRegressionModel":
#             self.model = LogisticRegressionModel(config)
#         elif config.model.model == "RandomForestModel":
#             self.model = RandomForestModel(config)
#         elif config.model.model == "SupportVectorModel":
#             self.model = SupportVectorModel(config)
#         elif config.model.model.lower() == "rwrm":
#             self.model = RWRM(config)
#         else:
#             raise ValueError("The model you requested '{}' is not implemented.".format(config.model.model))

#     def get_model(self):
#         return self.model


# class SKLearnModel:
#     """ Interface to seamlessly fit sklearn models into this framework for easier comparison"""

#     def __init__(self, model, config, *args, **kwargs):
#         self.model = model(*config.model.args, *args, **config.model.kwargs, **kwargs)
#         self.pos_weight = config.training.pos_weight
#         self.config = config
#         self.architectures = [self]
#         self.requires_sgd = False

#     def to(self, *args, **kwargs):
#         return self

#     def step(self, data, mask, eval_flag=False):
#         import numpy as np
#         sample_weight = np.ones_like(data.y[mask].detach().cpu().numpy())
#         sample_weight[data.y[mask].detach().cpu().numpy().astype(np.bool8)] = self.pos_weight

#         if not eval_flag:
#             if self.pos_weight is None:
#                 self.model.fit(data.x[mask].detach().cpu().numpy(), data.y[mask].detach().cpu().numpy())
#             else:
#                 self.model.fit(data.x[mask].detach().cpu().numpy(), data.y[mask].detach().cpu().numpy(),
#                                sample_weight=sample_weight)

#         out = self.model.predict_log_proba(data.x.detach().cpu().numpy())
#         accuracy = self.model.score(data.x[mask].detach().cpu().numpy(), data.y[mask].detach().cpu().numpy(),
#                                     sample_weight=sample_weight)

#         return torch.Tensor(out[:, 1].reshape((1, -1))), 1 - accuracy

#     def state_dict(self):
#         from pickle import dumps
#         return dumps(self.model)

#     def load_state_dict(self, state_dict):
#         from pickle import loads
#         self.model = loads(state_dict)


# class LogisticRegressionModel(SKLearnModel):
#     def __init__(self, config, *args, **kwargs):
#         from sklearn.linear_model import LogisticRegression
#         if "max_iter" not in kwargs.keys():
#             kwargs.update({"max_iter": 100000})
#         super(LogisticRegressionModel, self).__init__(model=LogisticRegression, config=config, class_weight="balanced",
#                                                       *args, **kwargs)


# class RandomForestModel(SKLearnModel):
#     def __init__(self, config, *args, **kwargs):
#         from sklearn.ensemble import RandomForestClassifier
#         super(RandomForestModel, self).__init__(model=RandomForestClassifier, config=config,
#                                                 class_weight="balanced_subsample", *args, **kwargs)


# class SupportVectorModel(SKLearnModel):
#     def __init__(self, config, *args, **kwargs):
#         from sklearn.svm import SVC
#         super(SupportVectorModel, self).__init__(model=SVC, config=config, probability=True, class_weight="balanced",
#                                                  *args, **kwargs)


# class RWRM:
#     def __init__(self, config, *args, **kwargs):
#         self.config = config
#         self.results = None
#         self.architectures = [self]
#         self.requires_sgd = False

#     def to(self, *args, **kwargs):
#         return self

#     def step(self, *args, eval_flag=False):
#         import subprocess
#         import pandas as pd
#         import numpy as np
#         import os
#         rwr_path = "./RWR-M"
#         input_file = self.config.name
#         output_file = input_file + "_results"
#         eps = 1e-16
#         data = pd.read_csv(processed_data_path(self.config)[1], header=0, sep="\t")

#         if not eval_flag:
#             true_training_hgnc = data["hgnc"][
#                 (data["truth"].values.astype(np.bool8) & data["train"].values.astype(np.bool8))]
#             true_training_hgnc.to_csv(os.path.join(rwr_path, input_file), header=False, index=False)
#             model_parameters = "Parameters_Example.txt" if "parameters" not in self.config.model.kwargs.keys() else \
#             self.config.model.kwargs["parameters"]

#             call = 'source ~/anaconda3/etc/profile.d/conda.sh && conda activate rwr && cd {} && Rscript RWR-M.R {}  Input_Files/{} {}'.format(
#                 rwr_path, input_file, model_parameters, output_file
#             )
#             p1 = subprocess.Popen([call], shell=True)
#             p1.wait()

#             results = pd.read_csv(os.path.join(rwr_path, "Output_Files", output_file + ".txt"), header=0, sep="\t",
#                                   index_col=0)

#             final_results = data.join(results, on="hgnc", how="left").replace(np.nan, 0)

#             self.results = final_results["Score"].values + eps

#         return torch.Tensor(self.results.reshape((1, -1))), np.nan

#     def state_dict(self):
#         from pickle import dumps
#         return dumps(self.results)

#     def load_state_dict(self, state_dict):
#         from pickle import loads
#         self.results = loads(state_dict)

# # TODO TransE, ComplEx, Node2Vec

import torch
import torch.nn as nn

from ..attack import Attack


class VMIFGSM(Attack):
    r"""
    VMI-FGSM in the paper 'Enhancing the Transferability of Adversarial Attacks through Variance Tuning
    [https://arxiv.org/abs/2103.15571], Published as a conference paper at CVPR 2021
    Modified from "https://github.com/JHL-HUST/VT"

    Distance Measure : Linf

    Arguments:
        model (nn.Module): model to attack.
        eps (float): maximum perturbation. (Default: 8/255)
        alpha (float): step size. (Default: 2/255)
        decay (float): momentum factor. (Default: 1.0)
        steps (int): number of iterations. (Default: 5)
        N (int): the number of sampled examples in the neighborhood. (Default: 20)
        beta (float): the upper bound of neighborhood. (Default: 3/2)

    Shape:
        - images: :math:`(N, C, H, W)` where `N = number of batches`, `C = number of channels`,        `H = height` and `W = width`. It must have a range [0, 1].
        - labels: :math:`(N)` where each value :math:`y_i` is :math:`0 \leq y_i \leq` `number of labels`.
        - output: :math:`(N, C, H, W)`.

    Examples::
        >>> attack = torchattacks.VMIFGSM(model, eps=8/255, steps=5, decay=1.0, N=20, beta=3/2)
        >>> adv_images = attack(images, labels)

    """

    def __init__(self, model, eps=8 / 255, alpha=2 / 255, steps=5, decay=1.0, N=20, beta=3 / 2):
        super().__init__("VMIFGSM", model)
        self.eps = eps
        self.steps = steps
        self.decay = decay
        self.alpha = alpha
        self.N = N
        self.beta = beta
        self._supported_mode = ['default', 'targeted']

    def forward(self, images, labels):
        r"""
        Overridden.
        """
        images = images.clone().detach().to(self.device) if self.use_device else images.clone().detach()
        labels = labels.clone().detach().to(self.device) if self.use_device else labels.clone().detach()

        if self._targeted:
            target_labels = self._get_target_label(images, labels)

        momentum = torch.zeros_like(images).detach().to(self.device) \
            if self.use_device else torch.zeros_like(images).detach()

        v = torch.zeros_like(images).detach().to(self.device) \
            if self.use_device else torch.zeros_like(images).detach()

        loss = nn.CrossEntropyLoss()

        adv_images = images.clone().detach()

        for _ in range(self.steps):
            adv_images.requires_grad = True
            outputs = self.model(adv_images)

            # Calculate loss
            if self._targeted:
                cost = -loss(outputs, target_labels)
            else:
                cost = loss(outputs, labels)

            # Update adversarial images
            adv_grad = torch.autograd.grad(cost, adv_images,
                                           retain_graph=False, create_graph=False)[0]

            grad = (adv_grad + v) / torch.mean(torch.abs(adv_grad + v), dim=(1, 2, 3), keepdim=True)
            grad = grad + momentum * self.decay
            momentum = grad

            # Calculate Gradient Variance
            GV_grad = torch.zeros_like(images).detach().to(self.device) \
                if self.use_device else torch.zeros_like(images).detach()

            for _ in range(self.N):
                neighbor_images = adv_images.detach() + \
                                  torch.randn_like(images).uniform_(-self.eps * self.beta, self.eps * self.beta)
                neighbor_images.requires_grad = True
                outputs = self.model(neighbor_images)

                # Calculate loss
                if self._targeted:
                    cost = -loss(outputs, target_labels)
                else:
                    cost = loss(outputs, labels)
                GV_grad += torch.autograd.grad(cost, neighbor_images,
                                               retain_graph=False, create_graph=False)[0]
            # obtaining the gradient variance
            v = GV_grad / self.N - adv_grad

            adv_images = adv_images.detach() + self.alpha * grad.sign()
            delta = torch.clamp(adv_images - images, min=-self.eps, max=self.eps)
            adv_images = torch.clamp(images + delta, min=0, max=1).detach()

        return adv_images

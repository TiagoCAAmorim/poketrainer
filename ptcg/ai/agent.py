"""Agente que joga usando uma rede treinada."""
from __future__ import annotations

import torch

from ..agents import Agent
from ..encode import encode
from .model import collate, load_checkpoint


class TorchAgent(Agent):
    name = 'model'

    def __init__(self, path, greedy=True, device='cpu', temperature=1.0):
        self.net, self.meta = load_checkpoint(path, device)
        self.device = device
        self.greedy = greedy
        self.temperature = temperature

    @torch.no_grad()
    def evaluate(self, g, prompt=None):
        """Retorna (probabilidades por opção, valor estimado em [-1, 1]) para o jogador da vez."""
        logits, value = self.net(collate([encode(g)], self.device))
        probs = torch.softmax(logits[0] / self.temperature, -1)
        return probs.cpu().numpy(), float(value[0])

    def act(self, g, prompt):
        probs, _ = self.evaluate(g, prompt)
        if self.greedy:
            return int(probs.argmax())
        return int(torch.multinomial(torch.as_tensor(probs), 1))

# node3090 Model Store — SHA256 Records
> Recorded 2026-06-12 (P21) at /opt/models reconciliation. Source of truth: `/opt/models/SHA256SUMS` on node3090.
> All `.gguf` files are `chattr +i` immutable — `sudo chattr -i <file>` required before any replace, re-hash + re-`+i` after.

```
99f19dd46961dcbb185c72d962d34ea8c00488a9b6da0ee5e21dbf1899d863e7  /opt/models/stronman/FLUX.2-dev-GGUF/flux2-dev-Q4_K_S.gguf
42c0c1a30fe2f30097ffedd554a94c2d6abc5f95b8a35ce99cd523f78ef6711b  /opt/models/bartowski/GLM-4.7-Flash-GGUF/GLM-4.7-Flash-Q4_K_M.gguf
f7ca062ce4f2c8ee09aa624d2158620eeaab7afb8ce8e4e9d23987738f2b8930  /opt/models/smthem/SenseNova-U1-8B-MoT-Merger-gguf/SenseNova-U1-8B-MoT-8step-Q4_K_S.gguf
79ad15a5ee3caddc3f4ff0db33a14454a5a3eb503d7fa1c1e35feafc579de486  /opt/models/lmstudio-community/Qwen3-Coder-30B-A3B-Instruct-GGUF/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
85f81a6a844d2f63c0fa64fa0899758429df791adb3886cdf09974d7429d0a3e  /opt/models/lmstudio-community/gemma-4-26B-A4B-it-GGUF/mmproj-gemma-4-26B-A4B-it-BF16.gguf
0ab52d910e0f641fa6618a028c8333f107095d450f1b0d5ff6fb515709cba355  /opt/models/lmstudio-community/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf
2d550cec247578b941e397f4bd4a0d51296eceb6d28b9c6290cd4105b0da5368  /opt/models/lmstudio-community/gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf
5e32614a9cdeaf6e30c2f316f0ded1b8edfad1aed1150611fd0b7e0ce36d56af  /opt/models/lmstudio-community/gemma-4-31B-it-GGUF/mmproj-gemma-4-31B-it-BF16.gguf
b5d6d9c7063068ce85130bae1d7851eadae1f81f9ecfae82112adffd4b736b45  /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/mmproj-Qwen3.6-27B-BF16.gguf
33625d8dc3a5dd8d88c324d47db58561b11f7072816287078bfe58b4c55782f9  /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf
083af225449463dd7c38bebc888f9dcad187b834d8b15e08c297dda37c968b50  /opt/models/lmstudio-community/NVIDIA-Nemotron-3-Nano-4B-GGUF/NVIDIA-Nemotron-3-Nano-4B-Q4_K_M.gguf
a53ccc46b2a48e4b29b97f1d5828902a9d8701e74c3f7c2f5331c136b66c728b  /opt/models/lmstudio-community/GLM-4.7-Flash-GGUF/GLM-4.7-Flash-Q4_K_M.gguf
68486d68176b924c5f126b0d25ab93e2b38458b607f46671d41c166f8c77c200  /opt/models/lmstudio-community/gemma-4-E4B-it-GGUF/mmproj-gemma-4-E4B-it-BF16.gguf
3f72a20a06f626c78e6c475ae07a64c88b2663149c0f6197b56bf7cf1f37585c  /opt/models/lmstudio-community/gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf
d0f0b016bb20e4e9f4978ef82123240a7f31750f675154e469664b8f292a0f1a  /opt/models/lmstudio-community/DeepSeek-R1-Distill-Qwen-32B-GGUF/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf
cbc303a666337cbac396c808d26a3875ab4290b1c6e47d2a157e26980ae5b421  /opt/models/lmstudio-community/Qwen3-14B-GGUF/Qwen3-14B-Q6_K.gguf
f110ab7c9ba662816496fe54286893e1f87830780ce03c30488aa53c79d788db  /opt/models/DavidAU/OpenAI-20B-NEO-CODE-DI-Uncensored-Q8_0.gguf/OpenAI-20B-NEO-CODE-DI-Uncensored-Q8_0.gguf
c426a30f3403fd3ba8f0b92e1de783ef1302a8b0b91ea6c32f2b4293944e3d9a  /opt/models/DavidAU/OpenAI-20B-NEO-HRR-DI-Uncensored-Q5_1.gguf/OpenAI-20B-NEO-HRR-DI-Uncensored-Q5_1.gguf
```

Primary serving model: `Qwen3.6-27B-Q4_K_M.gguf` = `33625d8d…782f9` (16,547,398,784 bytes — matches the byte-exact HF recovery from the 2026-06-11 incident).

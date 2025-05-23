import torch, platform
#print("Torch:", torch._version_)
print("Cuda  :", torch.version.cuda)
print("GPU?  :", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available()else"-")

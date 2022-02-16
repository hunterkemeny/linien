import setuptools

import linien

assert linien.__version__ != "dev"

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="linien-python-client",
    version=linien.__version__,
    author="Benjamin Wiegand",
    author_email="highwaychile@posteo.de",
    description="Python client for linien spectroscopy lock",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://hermitdemschoenenleben.github.io/linien/",
    # IMPORTANT: any changes have to be made in setup_client_and_gui.py
    # of flathub repo as well
    packages=["linien", "linien.client"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "numpy>=1.19.1",
        "paramiko>=2.9.2",
        "plumbum>=1.6.9",
        "rpyc>=4.0,<5.0",
        "scipy>=1.4.1",
        "uuid>=1.30",
    ],
    package_data={
        # IMPORTANT: any changes have to be made in pyinstaller.spec, too
        # (for the standalone installer)
        # IMPORTANT: any changes have to be made in setup_client_and_gui.py
        # of flathub repo as well
        "": ["VERSION"]
    },
)

from setuptools import setup

setup(
    name="python-asterisk",
    version="0.5.3",
    description="Compatibility shim that pulls in py-Asterisk==0.5.3",
    long_description="This meta-package ensures py-Asterisk==0.5.3 is installed where legacy projects expect python-asterisk.",
    long_description_content_type="text/plain",
    install_requires=["py-Asterisk==0.5.3"],
    python_requires=">=3.8",
)

from setuptools import find_packages, setup

setup(
    name="highagent",
    version="0.1.0",
    description="Scan local AI coding agent sessions and generate daily work reports with an LLM",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    entry_points={"console_scripts": ["highagent=highagent.cli:main"]},
)

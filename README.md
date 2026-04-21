
# Project-POC-Template

A less restrictive template to give POCs some structure and standards.

# Steps to take after creating a repository using this template

1. Enforce Main Branch Protection (Comment: To update JSON file to point to POC template)

> 1. Head into Settings of the repository on GitHub.
> 2. Under Code and automation, under Rules, under Rulesets, create a New Ruleset by the "Import a Ruleset" option and upload "Main Branch Protection Ruleset.json" file available in the new repository.
> 3. If you need to edit the Main Branch Protection Ruleset for whatever reason, please do it as a last resort.
> 4. If additional rules are required, please create an appriopriately named ruleset for them.

2. Update [docs/OVERVIEW.md](docs/OVERVIEW.md) file with the latest information

3. Create a staging branch. (Comment: Maybe a guide on why so and how do PRs work? Like "please refer to branching strategy" but a lesser version, just for education?)

4. Kick off your project (preferably with a virtual environment E.g. [venv](https://docs.python.org/3/library/venv.html) or [UV](https://docs.astral.sh/uv/#highlights)). Please refer to the [Project Structure](#project-structure) section below to understand where different files should go.

5. Update this README file after you are done with the previous steps.

# Project Structure

- [`.github/`](../.github): Contains the configuration files for Git Actions. (Comment: For Now)

- [`data/`](../data): Contains the data being used for the project.

- [`docs/`](../docs): Contains documentation for the project.

- [`src/`](../src): Contains the source code for the project.

- [`tests/`](../tests): Contains the tests cases for the project. (Comment: Has to be refined or maybe a guide on how to write test cases?)

# Monthly Commitments

1. For ongoing projects, please remember to at least update the repository [docs/OVERVIEW.md](../docs/OVERVIEW.md) monthly/biweekly.

2. If work is not being done on this repository, please do push the latest stable version monthly/biweekly too.

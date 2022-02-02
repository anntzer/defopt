from pathlib import Path

import nox
from nox import Session, session

python_versions = ['3.5', '3.6', '3.7', '3.8', '3.9', '3.10']
nox.options.sessions = ['tests', 'docs']
nox.options.reuse_existing_virtualenvs = True


@session(python=python_versions)
@nox.parametrize('old', [False, True])
def tests(session: Session, old: bool) -> None:
    """Run the tests."""
    args = session.posargs or ['--buffer']

    session.install('--upgrade', 'pip', 'setuptools', 'wheel', 'coverage')
    session.install('-e', '.')

    if old:
        # Oldest supported versions
        session.install('docutils==0.12', 'sphinxcontrib-napoleon==0.7.0')
        if session.python in ['3.5', '3.6', '3.7']:
            session.install(
                'typing_extensions==3.7.4', 'typing_inspect==0.5.0'
            )
        coverage_file = f'.coverage.{session.python}.oldest'
    else:
        coverage_file = f'.coverage.{session.python}'

    try:
        session.run(
            'coverage',
            'run',
            '--module',
            'unittest',
            *args,
            env={'COVERAGE_FILE': coverage_file},
        )
    finally:
        if session.interactive:
            session.notify('coverage', posargs=[])


@session
def coverage(session: Session) -> None:
    """Produce the coverage report."""
    args = session.posargs or ['report', '--show-missing']

    session.install('coverage')

    if not session.posargs and any(Path().glob('.coverage.*')):
        session.run('coverage', 'combine')

    session.run('coverage', *args)


@session
def docs(session: Session) -> None:
    """Produce the coverage report."""
    args = session.posargs or ['-b', 'html', 'doc/source', 'doc/build']

    session.install('-r', 'doc/requirements.txt')
    session.install('-e', '.')

    session.run('sphinx-build', *args)

import sys
from setuptools import setup


if sys.version_info < (3, 3):
    raise Exception('defopt requires Python 3.3+')


with open('README.rst') as readme:
    long_description = readme.read()

setup(
    name='defopt',
    version='0.1.0',
    description='Effortless argument parsing',
    long_description=long_description,
    author='evan_',
    author_email='evanunderscore@gmail.com',
    url='https://pypi.python.org/pypi/defopt',
    license='GNU General Public License v3',
    py_modules=['defopt'],
    test_suite='test_defopt',
    install_requires=['docutils'],
    tests_require=['coverage', 'nose'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
    ],
)

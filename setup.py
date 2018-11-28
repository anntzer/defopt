from setuptools import setup


with open('README.rst') as readme:
    long_description = readme.read()


setup(
    name='defopt',
    version='5.0.0',
    description='Effortless argument parser',
    long_description=long_description,
    author='evan_',
    author_email='evanunderscore@gmail.com',
    url='https://pypi.python.org/pypi/defopt',
    license='GNU General Public License v3',
    package_dir={'': 'src'},
    py_modules=['defopt'],
    test_suite='test_defopt',
    python_requires='>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*',
    install_requires=[
        'docutils',
        'sphinxcontrib-napoleon>=0.5.1',
        'typing_inspect>=0.3.1',
    ],
    extras_require={
        ':python_version<"3.3"': ['funcsigs'],
        ':python_version<"3.4"': ['enum34'],
        ':python_version<"3.5"': ['typing'],
        ':sys.platform=="win32"': ['colorama>=0.3.4'],
    },
    tests_require=[
        'mock;python_version<"3.3"',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
    ],
    keywords='argument parser parsing optparse argparse getopt docopt sphinx',
)

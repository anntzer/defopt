from setuptools import setup


with open('README.rst') as readme:
    long_description = readme.read()


setup(
    name='defopt',
    version='5.1.0',
    description='Effortless argument parser',
    long_description=long_description,
    author='Antony Lee',
    url='https://github.com/anntzer/defopt',
    license='MIT',
    py_modules=['defopt'],
    python_requires='>=3.5',
    install_requires=[
        'docutils',
        'sphinxcontrib-napoleon>=0.7.0',
    ],
    extras_require={
        ':python_version<"3.8"': [
            'typing_extensions>=3.7.4',  # Literal support.
            'typing_inspect>=0.3.1',
        ],
        ':sys.platform=="win32"': [
            'colorama>=0.3.4',
        ],
    },
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
    ],
    keywords='argument parser parsing optparse argparse getopt docopt sphinx',
)

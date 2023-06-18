from setuptools import setup


with open('README.rst') as readme:
    long_description = readme.read()


setup(
    name='defopt',
    description='Effortless argument parser',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    author='Antony Lee',
    url='https://github.com/anntzer/defopt',
    license='MIT',
    package_dir={'': 'lib'},
    py_modules=['defopt', '_defopt_napoleon'],
    python_requires='>=3.5',
    setup_requires=['setuptools_scm>=3.3'],  # fallback_version support.
    use_scm_version=lambda: {
        'version_scheme': 'post-release',
        'local_scheme': 'node-and-date',
        'fallback_version': '0+unknown',
    },
    install_requires=[
        'docutils>=0.12',  # First with wheels, for better setuptools compat.
    ],
    extras_require={
        ':python_version<"3.8"': [
            'importlib_metadata>=1.0',
            'typing_inspect>=0.8.0',
        ],
        ':python_version<"3.9"': [
            'pkgutil_resolve_name',
        ],
        ':sys.platform=="win32"': [
            'colorama>=0.3.4',
        ],
        'docs': [
            'sphinx>=4.4',
        ]
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
    ],
    keywords='argument parser parsing optparse argparse getopt docopt sphinx',
)

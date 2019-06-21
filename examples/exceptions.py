"""Example showing exception handling.

If the function raises an exception listed in the docstring using :raises:, the
traceback is suppressed.
"""
import defopt


def main(arg):
    """
    :param int arg: Don't set this to zero!
    :raises ValueError: If *arg* is zero.
    """
    if arg == 0:
        raise ValueError("Don't do this!")


if __name__ == "__main__":
    defopt.run(main)

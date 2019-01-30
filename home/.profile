# ~/.profile: executed by the command interpreter for login shells.
# This file is not read by bash(1), if ~/.bash_profile or ~/.bash_login
# exists.
# see /usr/share/doc/bash/examples/startup-files for examples.
# the files are located in the bash-doc package.

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.bin" ] ; then
    export PATH=$HOME/.bin:$PATH
fi

if [ -d "$HOME/.local/bin" ] ; then
    export PATH=$HOME/.local/bin:$PATH
fi

if [ -d "$HOME/.local/usr/bin" ] ; then
    export PATH=$HOME/.local/usr/bin:$PATH
fi

#if [ -d "/usr/lib/ccache" ]; then
#    export PATH=/usr/lib/ccache:$PATH
#fi

[[ -f ~/.local/share/env/env.ibm ]] && source ~/.local/share/env/env.ibm

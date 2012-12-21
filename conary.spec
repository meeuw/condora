Name: conary
Version: 2.4.8
Release: 1%{?dist}
Summary: Conary

License: MIT
URL: ftp://ftp.rpath.com/
Source0: conary-2.4.8.tar.bz2
Source1: conary-policy-1.2.tar.bz2

#BuildRequires:	
#Requires:	

%description
Conary

%prep
%setup -q
%setup -a 1

%build
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
make -C conary-policy-1.2 install DESTDIR=%{buildroot}


%files
/etc/*
/usr/bin/ccs2tar
/usr/bin/conary
/usr/bin/conary-debug
/usr/bin/cvc
/usr/bin/dbsh
/usr/share/*
/usr/lib64/conary
/usr/lib64/python2.7/site-packages/conary/*.py
/usr/lib64/python2.7/site-packages/conary/*.pyc
/usr/lib64/python2.7/site-packages/conary/*.pyo
/usr/lib64/python2.7/site-packages/conary/*.egg-info
/usr/lib64/python2.7/site-packages/conary/*.so
/usr/lib64/python2.7/site-packages/conary/build/*
/usr/lib64/python2.7/site-packages/conary/cmds/*
/usr/lib64/python2.7/site-packages/conary/conaryclient/*
/usr/lib64/python2.7/site-packages/conary/dbstore/*
/usr/lib64/python2.7/site-packages/conary/deps/*
/usr/lib64/python2.7/site-packages/conary/lib/*
/usr/lib64/python2.7/site-packages/conary/local/*
/usr/lib64/python2.7/site-packages/conary/sqlite3/*
/usr/lib64/python2.7/site-packages/conary/commitaction
/usr/lib64/python2.7/site-packages/conary/repository/*.py
/usr/lib64/python2.7/site-packages/conary/repository/*.pyc
/usr/lib64/python2.7/site-packages/conary/repository/*.pyo
/usr/libexec/conary/perlreqs.pl

%package rpm2cpio
Summary: rpm2cpio (conflicting)

%description rpm2cpio
rpm2cpio (conflicting with rpm)

%files rpm2cpio
/usr/bin/rpm2cpio

%package repository
Summary: repository
Requires: mod_python, mx, python-crypto, python-kid, python-pgsql, python-webob

%description repository
repository

%files repository
/usr/lib64/python2.7/site-packages/conary/repository/netrepos/
/usr/lib64/python2.7/site-packages/conary/repository/shimclient.py
/usr/lib64/python2.7/site-packages/conary/web/*
/usr/lib64/python2.7/site-packages/conary/server/*

%package policy
Summary: policy

%description policy
policy

%files policy
/usr/lib/*

%changelog
